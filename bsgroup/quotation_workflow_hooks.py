"""Add the shared, site-opt-in quotation workflow without replacing other hooks."""


def configure(namespace):
    def append(mapping, key, value, first=False):
        prior = mapping.get(key, [])
        values = [prior] if isinstance(prior, str) else list(prior)
        if value not in values:
            values.insert(0, value) if first else values.append(value)
        mapping[key] = values

    events = namespace['doc_events']
    base = 'bsgroup.oman_quotation_flow.'
    append(events.setdefault('Deal Cost Sheet', {}), 'on_submit', base+'dcs_submitted')
    for event, handler in [('validate','validate'), ('before_update_after_submit','validate'),
                           ('before_cancel','guard_cancel'), ('before_validate','before_validate'),
                           ('before_print','require_net_discount')]:
        append(events.setdefault('Quotation', {}), event, base+handler, first=event=='validate')
    for dt in ('Quotation','Deal Cost Sheet'):
        append(namespace['doctype_js'], dt, 'public/js/oman_quotation_flow.js')
    append(namespace['doctype_list_js'], 'Quotation', 'public/js/oman_quotation_flow_list.js')
