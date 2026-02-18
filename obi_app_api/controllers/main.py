from pprint import pprint
from odoo import models, http
from odoo.http import request
import odoo.models as odoo_models
from odoo.osv import expression

currencySpec = {
    'id': {},
    'name': {},
    'symbol': {},
    'position': {},
}

class Main(http.Controller):

    @http.route([
        '/obi_dashboard/shop',
        '/obi_dashboard/shop/page/<int:page>',
        '/obi_dashboard/shop/category/<model("product.public.category"):category>',
        '/obi_dashboard/shop/category/<model("product.public.category"):category>/page/<int:page>',
    ], auth='public', type='json')
    def shop(self, *args, **kwargs):
        # ===== Original Intention ======
        # this endpoint is intended for a mobile app
        # the mobile app should display the same data that is show in the website's /shop route
        # I want to achieve this by calling the same original method that handles /shop route,
        # but instead of rendering a html, just return a dictionary object with all variables that are available to the qweb renderer
        # this should include variables defined inside the qweb template with <t t-set="" t-value=""/>
        # so make a function that will use original odoo code as much as possible, but just before returning an html code, return a dictionary
        
        # real implementation, we can get the dictionary provided for the qweb view as context (this values here => `request.render("website_sale.products", values)`)
        # but values set inside the qweb with t-set, its better to replicate the code here
        # also t-if
        # making a renderer that will output an updated values dictionary instead of html is not practical, right?

        # Capture the context passed to the final render call of the original /shop controller
        orig_render = request.render
        try:
            def _capture_render(template, qcontext=None, *a, **kw):
                return qcontext or {}

            request.render = _capture_render
            # Import and call original WebsiteSale.shop implementation (unwrapped)
            from odoo.addons.website_sale.controllers.main import WebsiteSale as WebsiteSaleController
            # Call the original function behind the http.route decorator to avoid its wrapper
            shop_func = getattr(WebsiteSaleController, 'shop')
            # Use __wrapped__ to access the underlying function body (bypass route wrapper)
            if hasattr(shop_func, '__wrapped__'):
                result = shop_func.__wrapped__(WebsiteSaleController(), *args, **kwargs)
            else:
                result = WebsiteSaleController().shop(*args, **kwargs)
        finally:
            request.render = orig_render

        category = result.get('category')
        entries = None  # entries are categories, just named it like how the qweb template names it
        search = result.get('search')
        search_categories_ids = result.get('search_categories_ids')
        if category:
            entries = not search and category.child_id or category.child_id.filtered(lambda c: category.id in search_categories_ids)

        if not entries:
            parent = category.parent_id
            entries = not search and parent.child_id or parent.child_id.filtered(lambda c: parent.id in search_categories_ids)
        else:
            # populate needed data
            result['categories'] = result['categories'].web_read({
                'id': {},
                'display_name': {},
            })
        return result

    @http.route([
        '/obi_app/products/home',
    ], auth='public', type='json', website=True, sitemap=False)
    def products_home(self, *args, **kwargs):
        """
        Returns product home data suitable for mobile app including:
        - pricelist: current active pricelist
        - category: current category info
        - categories: list of categories available
        - products: paginated list of products
        - pagination: pagination info (current page, total pages, page size, total count)
        """
        category_obj = request.env['product.public.category']
        search = kwargs.get('search')
        category = int(kwargs.get('categoryId', 0))
        if category:
            category = category_obj.search([('id', '=', category)])
        page = int(kwargs.get('page', 1))
        
        # Get current pricelist
        website = request.env['website'].get_current_website()
        products_per_page = website.shop_ppg or 20
        pricelist = website.pricelist_id
        pricelist_data = {
            'id': pricelist.id,
            'display_name': pricelist.name,
            'currency_id': pricelist.currency_id.id,
            'currency_name': pricelist.currency_id.name,
        } if pricelist else False
        
        # Get categories - either subcategories of current category or root categories
        if category:
            # Get subcategories of the current category
            categories = category_obj.search([('parent_id', '=', category.id)])
            current_category = {
                'id': category.id,
                'name': category.name,
                'parent_id': category.parent_id.id if category.parent_id else False,
                'parents_and_self': category.parents_and_self.web_read({
                    'id': {},
                    'name': {},
                    'parent_id': {},
                }),
            }
        else:
            # Get root categories
            categories = category_obj.search([('parent_id', '=', False)])
            current_category = False
        
        # Format categories data using web_read
        categories_data = categories.web_read({
            'id': {},
            'display_name': {},
            'name': {},
            'parent_id': {},
            # 'product_template_ids': {'id': {}},
        })
        
        # Get products with pagination
        product_template_obj = request.env['product.template']

        website_domain = website.website_domain()
        domain = expression.AND([
            [
                ('is_published', '=', True),
                ('sale_ok', '=', True),
            ],
            website_domain
        ])

        # Filter by category if provided
        if category:
            domain = expression.AND([
                [
                    ('public_categ_ids', 'child_of', category.id),
                ],
                domain
            ])

        if search:
            domain = expression.AND([
                [
                    ('name', 'ilike', f'%{search}%'),
                ],
                domain
            ])
        
        # Search products
        total_products = product_template_obj.search_count(domain)
        products = product_template_obj.search(
            domain,
            offset=(page - 1) * products_per_page,
            limit=products_per_page,
            # order='display_name'
        )
        
        # Format products data using web_read
        products_data = products.web_read({
            'id': {},
            'display_name': {},
            'name': {},
            'description': {},
            'list_price': {},
            'categ_id': {
                'id': {},
                # 'display_name': {},
            },
            'public_categ_ids': {
                'id': {},
            },
        })
        # Add computed fields
        fiscal_position_sudo = website.fiscal_position_id.sudo()
        products_prices = products._get_sales_prices(pricelist, fiscal_position_sudo)
        currency_id = pricelist.currency_id if pricelist else website.currency_id
        currency_data = currency_id.web_read(currencySpec) if currency_id else []
        
        # Calculate pagination info
        total_pages = (total_products + products_per_page - 1) // products_per_page
        pagination = {
            'current_page': page,
            'total_pages': total_pages,
            'page_size': products_per_page,
            'total_count': total_products,
            'has_next': page < total_pages,
            'has_prev': page > 1,
        }
        
        return {
            'pricelist': pricelist_data,
            'category': current_category,
            'categories': categories_data,
            'products': products_data,
            'pagination': pagination,
            'products_prices': products_prices,
            'currency_data': len(currency_data) and currency_data[0],
        }

    @http.route([
        '/obi_app/shop',
    ], auth='public', type='json', website=True, sitemap=False)
    def app_shop(self, *args, **kwargs):
        from odoo.addons.website_sale.controllers.main import WebsiteSale as WebsiteSaleController
        result = WebsiteSaleController().shop(*args, **kwargs)

        categories = result.qcontext['categories']
        category = result.qcontext['category']
        current_category = {}
        if category:
            # do we still need this?
            categories = request.env['product.public.category'].search([('parent_id', '=', category.id)])
            current_category = {
                'id': category.id,
                'name': category.name,
                'parent_id': category.parent_id.id if category.parent_id else False,
                'parents_and_self': category.parents_and_self.web_read({
                    'id': {},
                    'name': {},
                    'parent_id': {},
                }),
            }
        categories_data = categories.web_read({
            'id': {},
            'display_name': {},
            'name': {},
            'parent_id': {},
            # 'product_template_ids': {'id': {}},
        })
        website = request.env['website'].get_current_website()
        pricelist = result.qcontext['pricelist']
        currency_id = pricelist.currency_id if pricelist else website.currency_id
        currency_data = currency_id.web_read(currencySpec) if currency_id else []
        pricelist_data = {
            'id': pricelist.id,
            'display_name': pricelist.name,
            'currency_id': pricelist.currency_id.id,
            'currency_name': pricelist.currency_id.name,
        } if pricelist else False

        bins = result.qcontext.pop('bins', None)  # bins is lazy method, pop it to prevent unnecessary computation
        products = result.qcontext['products']
        products_data = products.web_read({
            'id': {},
            'display_name': {},
            'name': {},
            'description': {},
            'list_price': {},
            'categ_id': {
                'id': {},
                # 'display_name': {},
            },
            'public_categ_ids': {
                'id': {},
            },
        })
        # Add computed fields

        result.qcontext['categories'] = categories_data
        result.qcontext['category'] = current_category
        result.qcontext['currency_data'] = len(currency_data) and currency_data[0]
        result.qcontext['pricelist'] = pricelist_data
        result.qcontext['products'] = products_data

        return result.qcontext

    @http.route([
        '/obi_app/profile',
    ], auth='user', type='json')
    def get_profile(self, *args, **kwargs):
        res = {
        }
        user = request.env.user
        if user:
            res.update({
                'user_id': user.id,
                'name': user.name,
                'email': user.email,
                'phone': user.partner_id.phone,
                'address': {
                    'city': user.partner_id.city,
                    'street': user.partner_id.street,
                    'street2': user.partner_id.street2,
                    'zip': user.partner_id.zip,
                    'state': {
                        'id': user.partner_id.state_id.id,
                        'name': user.partner_id.state_id.name,
                    },
                    'country': {
                        'id': user.partner_id.country_id.id,
                        'name': user.partner_id.country_id.name,
                    },
                },
            })
        return res
    
    @http.route([
        '/obi_app/profile/edit',
    ], auth='user', type='json')
    def update_profile(self, *args, **kwargs):
        valid_keys = [
            'name',
            'email',
            'phone',
            'city',
            'zip',
            'state_id',
            'country_id',
        ]

        values = {}
        for key in valid_keys:
            value = kwargs.get(key)
            if value:
                values[key] = value
        partner = request.env.user.partner_id
        partner.sudo().write(values)
        return {
            'is_success': True,
        }

    @http.route([
        '/obi_app/profile/edit/data',
    ], auth='public', type='json')
    def update_profile_data(self, *args, **kwargs):
        countries = request.env['res.country'].sudo().search([]).web_read({
            'id': {},
            'name': {},
            'code': {},
            'phone_code': {},
        })
        try:
            selected_country_id = int(kwargs.get('countryId', 0))
        except Exception:
            selected_country_id = 0
        states = []
        if not selected_country_id:
            selected_country_id = request.env.user.partner_id.country_id.id

        if selected_country_id:
            states = request.env['res.country.state'].sudo().search([('country_id', '=', selected_country_id)]).web_read({
                'id': {},
                'name': {},
            })
        return {
            'states': states,
            'countries': countries,
        }

    @http.route([
        '/obi_app/cart',
    ], auth='public', type='json', website=True, sitemap=False)
    def get_cart(self, *args, **kwargs):
        website = request.website
        from odoo.addons.website_sale.controllers.main import WebsiteSale as WebsiteSaleController
        result = WebsiteSaleController().cart(*args, **kwargs)
        order_id = result.qcontext['website_sale_order']
        # order_data = order_id.web_read({
        #     'website_order_line': {
        #         'fields': {
        #             'linked_line_id': {},
        #             'product_id': {},
        #             'name_short': {},
        #         }
        #     }
        # })
        # order_data = order_data[0]
        # qty_data = {}
        # for line in order_id.website_order_line:
        #     qty_data[line.id] = line._get_displayed_quantity()
        # for data_line in order_data['website_order_line']:
        #     data_line['displayed_quantity'] = qty_data[data_line['id']]
        # result.qcontext['website_sale_order'] = order_data

        res_order = {}
        if order_id:
            res_order = {
                'website_order_line': [],
                'amount_untaxed': order_id.amount_untaxed,
                'amount_tax': order_id.amount_tax,
                'amount_total': order_id.amount_total,
            }
            for line in order_id.website_order_line:
                product_price = 0
                if website.show_line_subtotals_tax_selection == 'tax_excluded':
                    product_price = line.price_subtotal
                else:
                    product_price = line.price_total
                res_order['website_order_line'].append({
                    'id': line.id,
                    'linked_line_id': line.linked_line_id,
                    'product_id': line.product_id.id,
                    'name_short': line.name_short,
                    'displayed_quantity': line._get_displayed_quantity(),
                    'product_price': product_price,
                })
        result.qcontext['website_sale_order'] = res_order

        currency = result.qcontext['currency']
        result.qcontext['currency'] = {
            'id': currency.id,
            'name': currency.name,
            'symbol': currency.symbol,
            'position': currency.position,
        }

        return {
            'cart_data': result.qcontext,
        }

    @http.route([
        '/shop/cart/skip_payment',
    ], auth='public', type='json', website=True, sitemap=False)
    def skip_payment(self, *args, **kwargs):
        order = request.website.sale_get_order()
        if order:
            order.action_confirm()
        return {
            'order_id': order and order.id,
        }

    @http.route([
        '/obi_app/orders',
    ], auth='public', type='json', website=True, sitemap=False)
    def get_orders(self, *args, **kwargs):
        from odoo.addons.sale.controllers.portal import CustomerPortal as CustomerPortalController
        result = CustomerPortalController().portal_my_orders(*args, **kwargs)
        orders_data = result.qcontext['orders'].web_read({
            'name': {},
            'date_order': {},
            'locked': {},
            'amount_total': {},
            'currency_id': {
                'fields': currencySpec,
            },
        })
        result.qcontext['orders'] = orders_data
        return {
            'orders_data': result.qcontext,
        }

    @http.route([
        '/obi_app/single_order',
    ], auth='public', type='json', website=True, sitemap=False)
    def get_single_order(self, *args, **kwargs):
        from odoo.addons.sale.controllers.portal import CustomerPortal as CustomerPortalController
        result = CustomerPortalController().portal_order_page(*args, **kwargs)
        sale_order = result.qcontext['sale_order']
        order_data = {}
        if sale_order:
            order_data.update(sale_order.web_read({
                'name': {},
                'date_order': {},
                'amount_untaxed': {},
                'amount_tax': {},
                'amount_total': {},
                'currency_id': {
                    'fields': currencySpec,
                },
            })[0])
        result.qcontext['sale_order'] = order_data


        lines_to_report = sale_order._get_order_lines_to_report()

        # populate: order lines
        current_subtotal = 0
        lines = []
        for index, line in enumerate(lines_to_report):
            current_subtotal = current_subtotal + line.price_subtotal
            line_data = {
                'id': line.id,
                'product_id': line.product_id.id,
                'product_idxxx': line.product_id,

                'product_name': line.name,
                'display_type': line.display_type,
                'product_uom_qty': line.product_uom_qty,
                'product_uom': {
                    'id': line.product_uom.id,
                    'name': line.product_uom.name,
                },
                'discount': line.discount,
                'price_unit': line.price_unit,
                'discount_amount': (1-line.discount / 100.0) * line.price_unit,
                'is_display_discount': True in [line.discount > 0 for line in sale_order.order_line],
                'taxes': ', '.join(map(lambda x: (x.description or x.name), line.tax_id)),
                'is_downpayment': line.is_downpayment,
                'subtotal': line.price_subtotal,
            }
            current_section = None
            if line.display_type == 'line_section':
                # does section resets subtotal? see this in og template output
                current_section = line
                current_subtotal = 0
            line_last = index == len(lines_to_report) - 1
            line_data['is_display_subtotal'] = current_section and (line_last or lines_to_report[index+1].display_type == 'line_section') and not line.is_downpayment
            line_data['current_subtotal'] = current_subtotal
            lines.append(line_data)
        
            is_same_invoice_and_shipping = sale_order.partner_shipping_id == sale_order.partner_invoice_id
            customer_info = {
                'is_same_invoice_and_shipping': is_same_invoice_and_shipping,
            }
            # <small t-if="sale_order.partner_id == sale_order.partner_invoice_id == sale_order.env.user.partner_id">
            billing_address_data = extract_contact_widget_data(sale_order.partner_invoice_id)
            customer_info['partner_invoice_id'] = billing_address_data
            if not is_same_invoice_and_shipping:
                customer_info['partner_shipping_id'] = extract_contact_widget_data(sale_order.partner_shipping_id)
            else:
                customer_info['partner_shipping_id'] = billing_address_data
            invoices = sale_order.invoice_ids.filtered(lambda i: i.state not in ['draft', 'cancel']).sorted('date', reverse=True)[:3]
            # customer_info['invoices']
            is_show_invoices = invoices and sale_order.state in ['sale', 'cancel']
            invoices_data = []
            if is_show_invoices:
                for i in invoices:
                    payment_state_text = ''
                    is_authorized_tx_ids = bool(i.authorized_transaction_ids)
                    if i.payment_state in ('paid', 'in_payment'):
                        payment_state_text = 'Paid'
                    elif i.payment_state == 'reversed':
                        payment_state_text = 'Reversed'
                    elif is_authorized_tx_ids:
                        payment_state_text = 'Authorized'
                    else:
                        payment_state_text = 'Waiting Payment'

                    invoices_data.append({
                        'id': i.id,
                        'name': i.name,
                        'payment_state_text': payment_state_text,
                        'invoice_date': i.invoice_date,
                    })
        
        delivery_orders = sale_order.picking_ids.filtered(
            lambda picking: picking.picking_type_id.code == 'outgoing'
        ).sorted('date', reverse=True)[:3]

        returns = sale_order.picking_ids.filtered(
            lambda picking: picking.picking_type_id.code == 'incoming'
        )

        def keep_query():
            # should this return a http query params that will be used by pdf reports? ? ?
            return ''

        shipping_data = {
            "delivery_orders": [
                {
                    "id": picking.id,
                    "name": picking.name,
                    "report_url": f"/my/picking/pdf/{picking.id}?{keep_query()}",
                    "return_url": f"/my/picking/return/pdf/{picking.id}?{keep_query()}" if picking.state == "done" else None,
                    "state": picking.state,
                    "status_label": (
                        "Shipped" if picking.state == "done"
                        else "Cancelled" if picking.state == "cancel"
                        else "Preparation" if picking.state in ["draft", "waiting", "confirmed", "assigned"]
                        else None
                    ),
                    # "status_label": 'Shipped',
                    "status_type": (
                        "success" if picking.state == "done"
                        else "danger" if picking.state == "cancel"
                        else "info" if picking.state in ["draft", "waiting", "confirmed", "assigned"]
                        else None
                    ),
                    # "status_type": 'success',
                    "date_done": picking.date_done,
                    "is_show_scheduled_date": picking.state in ['draft', 'waiting', 'confirmed', 'assigned'],
                    "scheduled_date": picking.scheduled_date,
                }
                for picking in delivery_orders
            ],
            "returns": [
                {
                    "id": picking.id,
                    "name": picking.name,
                    "report_url": f"/my/picking/pdf/{picking.id}?{keep_query()}",
                    "state": picking.state,
                    "status_label": (
                        "Received" if picking.state == "done"
                        else "Cancelled" if picking.state == "cancel"
                        else "Awaiting arrival" if picking.state in ["draft", "waiting", "confirmed", "assigned"]
                        else None
                    ),
                    "status_type": (
                        "success" if picking.state == "done"
                        else "danger" if picking.state == "cancel"
                        else "info" if picking.state in ["draft", "waiting", "confirmed", "assigned"]
                        else None
                    ),
                    "date_done": picking.date_done,
                    '': picking.state in ['draft', 'waiting', 'confirmed', 'assigned'],
                    "scheduled_date": picking.scheduled_date,
                }
                for picking in returns
            ]
        }

        terms_data = {
            # WIP
            'is_terms_html': sale_order.terms_type == 'html',
            'terms_link': '',
                #     <t t-set="tc_url" t-value="'%s/terms' % (sale_order.get_base_url())"/>
                #     <em>Terms &amp; Conditions: <a href="/terms"><t t-out="tc_url"/></a></em>
                # </t>
                # <t t-else="">
                #     <em t-field="sale_order.note"/>
                # </t>
        }

        result.qcontext['sale_order']['lines'] = lines
        result.qcontext['invoices'] = invoices_data
        result.qcontext['customer_info'] = customer_info
        result.qcontext['shipping_data'] = shipping_data
        return {
            'order_data': result.qcontext,
        }

def extract_contact_widget_data(partner):
    """
    Extracts contact info from a res.partner record for use in a React Native ContactWidget.
    :param partner: res.partner record (browse record)
    :return: dict with contact fields
    """
    return {
        "name": partner.name,
        "address": partner.street,
        "city": partner.city,
        "country": partner.country_id.name if partner.country_id else "",
        "phone": partner.phone,
        "mobile": partner.mobile,
        "website": partner.website,
        "email": partner.email,
        "vat": partner.vat,
        "vatLabel": partner.env['ir.model.fields']._get('res.partner', 'vat').field_description if partner.vat else "VAT",
        "fields": [
            field for field in [
                "address" if partner.street else None,
                "city" if partner.city else None,
                "phone" if partner.phone else None,
                "mobile" if partner.mobile else None,
                "website" if partner.website else None,
                "email" if partner.email else None,
                "vat" if partner.vat else None,
            ] if field
        ],
        "options": {
            "no_marker": False,
            "phone_icons": True,
        }
    }
