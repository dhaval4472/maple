"""Shared, editable site content.

Everything here mirrors information already published elsewhere on the site.
No prices, coverage promises or review aggregates are invented.
"""

CALLBACK_WINDOWS = [
    ("Anytime today", "Anytime today"),
    ("9:00–11:00 AM", "9:00–11:00 AM"),
    ("11:00 AM–1:00 PM", "11:00 AM–1:00 PM"),
    ("1:00–3:00 PM", "1:00–3:00 PM"),
    ("3:00–5:00 PM", "3:00–5:00 PM"),
    ("Any weekday", "Any weekday"),
]

DROP_OFF_WINDOWS = [
    ("9:00–11:00 AM", "9:00–11:00 AM"),
    ("11:00 AM–1:00 PM", "11:00 AM–1:00 PM"),
    ("1:00–3:00 PM", "1:00–3:00 PM"),
    ("3:00–5:00 PM", "3:00–5:00 PM"),
]

SERVICES = [
    {
        "slug": "collision",
        "title": "Collision repair",
        "short_title": "Collision",
        "category": "body",
        "category_label": "Body & glass",
        "icon": "ico-collision",
        "material_icon": "car_crash",
        "summary": "Panel repair, bumper restoration and structural alignment after a collision.",
        "intro": (
            "A collision can damage far more than the panel you can see. We inspect the "
            "structure, safety systems and parts availability before the repair plan is set, "
            "then explain what MPI needs and what happens next."
        ),
        "included": [
            "Damage inspection and written estimate",
            "Teardown, structural pull and panel replacement",
            "Colour-matched refinish and reassembly",
            "MPI claim coordination on approved work",
        ],
        "time": "2–5 business days typical",
        "claims": "MPI Direct Repair shop",
        "note": "Repair scope and coverage are confirmed after inspection. MPI makes the coverage decision.",
        "search": "collision repair accident body panel bumper frame mpi claim structural dent",
        "faqs": [
            (
                "Do I need an MPI claim number before I come in?",
                "No. We can look at the vehicle and explain the repair side first. If you have a claim number, bring it so we can talk through the MPI process together.",
            ),
            (
                "Will the estimate change after teardown?",
                "It can. Hidden damage is common in collisions. If the scope changes, we call you before doing the extra work.",
            ),
        ],
        "tools": ["repair-estimate", "mpi-claim-navigator", "repair-or-replace"],
    },
    {
        "slug": "windshield",
        "title": "Windshield repair & replacement",
        "short_title": "Windshield",
        "category": "body",
        "category_label": "Body & glass",
        "icon": "ico-windshield",
        "material_icon": "car_repair",
        "summary": "Stone-chip repair or a full windshield replacement, sealed to factory spec.",
        "intro": (
            "A small chip is not always a small problem. Whether a chip can be repaired "
            "depends on its size, depth and location. We assess the glass in person and "
            "explain repair-versus-replacement before any work starts."
        ),
        "included": [
            "Damage assessment and repair-versus-replace advice",
            "Resin injection for repairable chips",
            "Full glass replacement with fresh urethane sealing",
            "MPI direct billing on eligible claims",
        ],
        "time": "30 min chip · 2–3 hr replacement",
        "claims": "MPI direct eligible",
        "note": "A repair or replacement recommendation is confirmed after the glass is inspected.",
        "search": "windshield glass chip crack replacement stone rock auto glass mpi claim",
        "faqs": [
            (
                "Can a chip be repaired instead of replaced?",
                "Sometimes. Size, depth and location matter, especially if the damage sits in the driver's line of sight. The chip checker gives a preliminary guide, but the final call is made after inspection.",
            ),
            (
                "Can I drive after a windshield replacement?",
                "We follow the urethane manufacturer's drive-away time and give you the specific instruction for your vehicle when you pick it up.",
            ),
        ],
        "tools": ["repair-estimate", "windshield-chip-checker", "repair-or-replace"],
    },
    {
        "slug": "paint",
        "title": "Dent repair & painting",
        "short_title": "Dent & paint",
        "category": "body",
        "category_label": "Body & glass",
        "icon": "ico-paint",
        "material_icon": "format_paint",
        "summary": "Dent removal, panel prep, colour matching and clear-coat finishing.",
        "intro": (
            "Dent repair is part straightening and part finish work. We match the colour "
            "to your vehicle, prep the panel properly and finish with a clear coat so the "
            "repair blends with the surrounding paint."
        ),
        "included": [
            "Dent pull and panel straightening",
            "Surface prep and primer",
            "Computerized colour match in the spray booth",
            "Clear coat, curing and final polish",
        ],
        "time": "1–3 business days",
        "claims": "Private or MPI approved",
        "note": "Colour match and final finish are confirmed after the panel is inspected.",
        "search": "dent paint painting refinish scratch bumper colour match clear coat body",
        "faqs": [
            (
                "Can you match my factory colour?",
                "We use a computerized colour match and test the blend before refinishing. Some colours and finishes need a blend into adjacent panels for the best result.",
            ),
            (
                "Is a paint repair covered by MPI?",
                "That depends on your claim. We can discuss the repair side, but MPI decides what the claim covers.",
            ),
        ],
        "tools": ["repair-estimate", "repair-or-replace"],
    },
    {
        "slug": "mechanical",
        "title": "Mechanical repair",
        "short_title": "Mechanical",
        "category": "mechanical",
        "category_label": "Mechanical",
        "icon": "ico-mechanical",
        "material_icon": "build",
        "summary": "Engine, suspension and drivetrain work, plus regular maintenance.",
        "intro": (
            "Mechanical problems are easier to solve when the symptom is described clearly. "
            "We road test, inspect and explain the cause before recommending parts or repairs."
        ),
        "included": [
            "Road test and symptom interview",
            "Component inspection and repair plan",
            "Suspension, steering and drivetrain service",
            "Repair confirmation before pickup",
        ],
        "time": "Varies with diagnosis",
        "claims": "Private mechanical work",
        "note": "Timing and scope are confirmed after diagnosis.",
        "search": "mechanical repair engine suspension drivetrain tune up maintenance noise",
        "faqs": [
            (
                "Should I describe the noise or just bring it in?",
                "Both help. Tell us when you hear it, what it sounds like and whether it changes with speed, braking or turning. That shortens the diagnosis.",
            ),
            (
                "Do you work on all makes?",
                "We work on passenger cars, SUVs, vans and light pickups. Call first for heavy fleet vehicles or heavily modified builds.",
            ),
        ],
        "tools": ["repair-estimate", "repair-or-replace"],
    },
    {
        "slug": "diagnostics",
        "title": "Computerized diagnostics",
        "short_title": "Diagnostics",
        "category": "mechanical",
        "category_label": "Mechanical",
        "icon": "ico-diagnostics",
        "material_icon": "settings_input_component",
        "summary": "OBD-II scans, live data and electrical fault finding.",
        "intro": (
            "A fault code points to a system, not always to the failed part. We use scan "
            "data and targeted tests to isolate the cause before parts are ordered."
        ),
        "included": [
            "OBD-II scan and fault-code reading",
            "Live sensor data and voltage checks",
            "Component testing to isolate the cause",
            "A plain-language explanation before parts are ordered",
        ],
        "time": "45–60 minutes",
        "claims": "Private mechanical work",
        "note": "A diagnostic fee and repair scope are confirmed before work begins.",
        "search": "computerized diagnostics obd2 scan electrical sensor warning light fault code",
        "faqs": [
            (
                "Can you tell me the problem from the code alone?",
                "Not reliably. The code narrows the system. Testing is what confirms the cause.",
            ),
            (
                "Will the warning light stay off after repair?",
                "We clear the code after the repair and verify it does not return during our check. Some systems need a drive cycle to complete their self-tests.",
            ),
        ],
        "tools": ["repair-estimate", "repair-or-replace"],
    },
    {
        "slug": "check-engine",
        "title": "Check-engine diagnostics",
        "short_title": "Check engine",
        "category": "mechanical",
        "category_label": "Mechanical",
        "icon": "ico-check-engine",
        "material_icon": "warning",
        "summary": "That light is a starting point. We find the cause before swapping parts.",
        "intro": (
            "A check-engine light can mean anything from a loose fuel cap to a sensor "
            "fault. We scan the code, check the symptom history and test the affected "
            "system before recommending a repair."
        ),
        "included": [
            "Code scan and symptom history",
            "Targeted tests for the affected system",
            "Repair recommendation with a cost range",
            "Post-repair code clear and verification",
        ],
        "time": "45–60 minutes",
        "claims": "Private mechanical work",
        "note": "A cost range is not a final quote. The scope is confirmed after testing.",
        "search": "check engine light warning lamp emissions fault code diagnostic",
        "faqs": [
            (
                "Is it safe to keep driving with the light on?",
                "It depends on the light and the symptom. A steady light is different from a flashing light. If it is flashing or the vehicle is running poorly, call us before driving further.",
            ),
            (
                "Do you charge for the scan?",
                "Ask when you call. We confirm any diagnostic charge before the vehicle is worked on.",
            ),
        ],
        "tools": ["repair-estimate", "repair-or-replace"],
    },
    {
        "slug": "safety",
        "title": "Safety inspection",
        "short_title": "Safety inspection",
        "category": "maintenance",
        "category_label": "Maintenance",
        "icon": "ico-safety",
        "material_icon": "verified_user",
        "summary": "MPI safety inspections, with repairs handled in the same visit if needed.",
        "intro": (
            "A safety inspection is a checklist, not a guess. We inspect the required "
            "items, explain any failures clearly and give you repair options before "
            "the work continues."
        ),
        "included": [
            "Full MPI safety inspection checklist",
            "Clear pass/fail findings",
            "Repair options for failed items",
            "Certificate issued on a pass",
        ],
        "time": "Same-day in most cases",
        "claims": "MPI safety certificate",
        "note": "A certificate is issued only when the vehicle passes the inspection.",
        "search": "vehicle safety inspection mpi certification roadworthy certificate",
        "faqs": [
            (
                "What should I bring?",
                "Bring the vehicle registration and your driver's licence. If you have an MPI claim or prior inspection, bring that paperwork too.",
            ),
            (
                "What happens if the vehicle fails?",
                "We explain which items failed and what repair options are available. You decide whether to proceed.",
            ),
        ],
        "tools": ["repair-estimate", "mpi-claim-navigator"],
    },
    {
        "slug": "brakes",
        "title": "Brake inspection & service",
        "short_title": "Brakes",
        "category": "maintenance",
        "category_label": "Maintenance",
        "icon": "ico-brakes",
        "material_icon": "disc_full",
        "summary": "Pads, rotors, calipers and fluid — checked before they become urgent.",
        "intro": (
            "Brake noise, a soft pedal or a longer stopping distance all deserve a look. "
            "We measure the pads and rotors, check the lines and explain what needs "
            "attention now versus what can wait."
        ),
        "included": [
            "Wheels-off pad and rotor measurement",
            "Caliper, hose and brake-line inspection",
            "Pad and rotor replacement if needed",
            "Brake fluid check and bleed",
        ],
        "time": "1–2 hours per axle",
        "claims": "Wear item · private rates",
        "note": "Brake work is quoted after inspection. We confirm the scope before starting.",
        "search": "brake brakes pads rotors caliper squeal grinding soft pedal inspection service",
        "faqs": [
            (
                "Why are my brakes squealing?",
                "It can be worn pads, glazed surfaces, a wear indicator or something else. A wheels-off inspection is the reliable way to tell.",
            ),
            (
                "Can I wait on a brake repair?",
                "We explain the measurement and the risk so you can decide. If a safety item is below spec, we will say so plainly.",
            ),
        ],
        "tools": ["repair-estimate", "repair-or-replace"],
    },
    {
        "slug": "oil",
        "title": "Oil changes",
        "short_title": "Oil change",
        "category": "maintenance",
        "category_label": "Maintenance",
        "icon": "ico-oil",
        "material_icon": "oil_barrel",
        "summary": "Synthetic or conventional oil with a filter change and a quick look underneath.",
        "intro": (
            "An oil change is also a chance to look underneath the vehicle. We match "
            "the oil to your vehicle, replace the filter and note anything that needs "
            "attention later."
        ),
        "included": [
            "Oil grade matched to your vehicle",
            "Filter replacement and drain-plug check",
            "Fluid top-up and visual inspection",
            "Ask about current oil-change pricing",
        ],
        "time": "30–45 minutes",
        "claims": "Routine maintenance",
        "note": "Oil pricing depends on the oil grade and filter. Call for the current price.",
        "search": "oil change synthetic conventional filter fluid maintenance",
        "faqs": [
            (
                "How often should I change my oil?",
                "Follow the owner's manual for your vehicle and driving conditions. We can note the interval on your invoice.",
            ),
            (
                "Do I need an appointment?",
                "Call ahead so we can set aside time. Same-day service depends on the schedule.",
            ),
        ],
        "tools": ["repair-estimate", "repair-or-replace"],
    },
    {
        "slug": "wheels",
        "title": "Wheel balancing",
        "short_title": "Wheel balancing",
        "category": "maintenance",
        "category_label": "Maintenance",
        "icon": "ico-wheels",
        "material_icon": "tire_repair",
        "summary": "Spin balancing to chase down vibration and uneven tire wear.",
        "intro": (
            "Vibration at speed often comes from wheel balance, tire wear or a bent "
            "wheel. We spin balance the wheels and inspect the tires so the next step "
            "is based on what we find."
        ),
        "included": [
            "High-speed spin balance",
            "Wheel weight correction",
            "Tread and sidewall inspection",
            "Vibration road-test notes",
        ],
        "time": "30–60 minutes",
        "claims": "Routine maintenance",
        "note": "If the vibration is not balance-related, we explain the next diagnostic step.",
        "search": "wheel balancing tire vibration wobble alignment spin balance tread",
        "faqs": [
            (
                "Will balancing fix a vibration?",
                "It fixes balance-related vibration. If the tire or wheel is damaged, balancing alone will not solve it. We inspect and tell you what we find.",
            ),
            (
                "Do you do wheel alignments?",
                "Ask when you call. We will confirm what is available for your vehicle.",
            ),
        ],
        "tools": ["repair-estimate", "repair-or-replace"],
    },
]

SERVICE_BY_SLUG = {service["slug"]: service for service in SERVICES}

TOOLS = [
    {
        "slug": "repair-estimate",
        "title": "Repair estimate",
        "icon": "request_quote",
        "tagline": "A planning range from the shop's own prices.",
        "summary": "Pick a service and describe the vehicle. See the range the shop owner has set for that work — with a plain reminder that it is not a quote.",
        "time": "2 minutes",
        "cta": "See a planning range",
    },
    {
        "slug": "mpi-claim-navigator",
        "title": "MPI claim navigator",
        "icon": "verified_user",
        "tagline": "Work out the next step for your claim.",
        "summary": "Answer a few questions about your claim, vehicle and paperwork. Get a plain-language next step and a checklist.",
        "time": "2 minutes",
        "cta": "Start the navigator",
    },
    {
        "slug": "windshield-chip-checker",
        "title": "Windshield chip checker",
        "icon": "car_repair",
        "tagline": "Repair or replace? Get a preliminary guide.",
        "summary": "Describe the chip size, type and location. See whether it is usually repairable or needs an in-person assessment.",
        "time": "1 minute",
        "cta": "Check a chip",
    },
    {
        "slug": "repair-or-replace",
        "title": "Repair vs replace",
        "icon": "compare_arrows",
        "tagline": "Understand the trade-offs before you decide.",
        "summary": "Compare repair and replacement considerations for your damage, vehicle and claim situation — without a price promise.",
        "time": "2 minutes",
        "cta": "Compare options",
    },
]

TOOL_BY_SLUG = {tool["slug"]: tool for tool in TOOLS}

REVIEWS = [
    {
        "author": "Jorge H. Orellana",
        "quote": "We had a great experience at Maple Leaf Auto Body. The staff were very knowledgeable. Highly recommend.",
        "rating": 5,
        "category": "body",
        "category_label": "Body work",
        "source_label": "Customer feedback",
    },
    {
        "author": "Trevor",
        "quote": "Went in for a quick job and they were able to get me in right away for a fair price. Great guys.",
        "rating": 5,
        "category": "quick",
        "category_label": "Quick service",
        "source_label": "Customer feedback",
    },
    {
        "author": "Mandeep Brar",
        "quote": "Great job. No waiting — just come fix your vehicle same time. Very good atmosphere.",
        "rating": 5,
        "category": "quick",
        "category_label": "Quick service",
        "source_label": "Customer feedback",
    },
]

REPAIR_STORY_CATEGORIES = [
    ("body", "Body & glass"),
    ("mechanical", "Mechanical"),
    ("maintenance", "Maintenance"),
]
