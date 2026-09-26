"""Safety gates run before any form is filled: scam / data-harvesting checks and the flagged registry.

    from careeros.safety.scam import check_posting, check_form_fields, auto_submit_allowed
    from careeros.safety import registry

CLI: `careeros safety check <job_id>`, `careeros safety fields <job_id> --labels-json -`,
`careeros safety flag <company> [--domain D] --reason R`.
"""
