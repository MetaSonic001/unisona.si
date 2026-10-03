"""Use-case templates. Each one pre-fills persona, goals, tools, analysis and handoff."""
from __future__ import annotations

from typing import Any

E = lambda name, typ, desc: {"name": name, "type": typ, "description": desc}  # noqa: E731

TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "customer-support", "name": "Customer Support", "icon": "headset", "category": "Support",
        "description": "Answers questions from your docs, resolves issues and hands off to a human when needed.",
        "persona": {"name": "Aria", "role": "customer support specialist",
                    "goals": ["Resolve the customer's issue using the knowledge base", "Collect order or account details when needed", "Hand off to a human for refunds, complaints or anything you cannot verify"]},
        "analysis": {"extraction": [E("issue_category", "string", "Short category of the customer's issue"), E("order_id", "string", "Order or ticket ID mentioned, if any"), E("resolved", "boolean", "Whether the issue was resolved")],
                     "dispositions": ["resolved", "escalated", "pending_customer", "unresolved"]},
    },
    {
        "id": "receptionist", "name": "AI Receptionist", "icon": "phone", "category": "Front desk",
        "description": "Greets callers, answers FAQs, books appointments and routes calls 24/7.",
        "persona": {"name": "Maya", "role": "front-desk receptionist",
                    "goals": ["Greet warmly and identify the caller's need", "Answer FAQs about hours, location and services", "Book, reschedule or cancel appointments", "Take a message or transfer when the caller asks for a person"]},
        "analysis": {"extraction": [E("caller_name", "string", "Caller's name"), E("reason", "string", "Reason for calling"), E("appointment_booked", "boolean", "Whether an appointment was booked")],
                     "dispositions": ["appointment_booked", "question_answered", "message_taken", "transferred"]},
    },
    {
        "id": "lead-qualification", "name": "Lead Qualification", "icon": "filter", "category": "Sales",
        "description": "Qualifies inbound leads with BANT questions, scores them and books meetings with sales.",
        "persona": {"name": "Rohan", "role": "sales development representative",
                    "goals": ["Understand the lead's need, budget, authority and timeline", "Score the lead honestly", "Book a meeting with sales for qualified leads", "Capture contact details"]},
        "analysis": {"extraction": [E("budget", "string", "Budget mentioned"), E("timeline", "string", "Purchase timeline"), E("decision_maker", "boolean", "Is the person the decision maker"), E("need", "string", "Primary need"), E("lead_score", "number", "0-100 qualification score")],
                     "dispositions": ["qualified", "nurture", "not_a_fit", "meeting_booked"]},
    },
    {
        "id": "cold-calling", "name": "Outbound Sales", "icon": "phone-outgoing", "category": "Sales",
        "description": "Runs outbound sales calls, handles objections politely and books demos.",
        "persona": {"name": "Kabir", "role": "outbound sales executive",
                    "goals": ["Introduce yourself and the reason for the call within 15 seconds", "Ask permission to continue", "Qualify interest and handle objections respectfully", "Book a follow-up or demo", "Respect do-not-call requests immediately"]},
        "analysis": {"extraction": [E("interest_level", "string", "high, medium, low or none"), E("objection", "string", "Main objection raised"), E("callback_time", "string", "Preferred callback time")],
                     "dispositions": ["interested", "not_interested", "callback_requested", "do_not_call", "meeting_booked", "wrong_number"]},
    },
    {
        "id": "technical-support", "name": "Technical Support", "icon": "wrench", "category": "Support",
        "description": "Troubleshoots step by step from your docs and escalates complex problems.",
        "persona": {"name": "Dev", "role": "technical support engineer",
                    "goals": ["Diagnose the problem with targeted questions", "Give clear step-by-step fixes from the documentation", "Escalate bugs or outages with a detailed summary"]},
        "analysis": {"extraction": [E("product_area", "string", "Product area affected"), E("error_message", "string", "Exact error quoted"), E("fixed", "boolean", "Whether the fix worked")],
                     "dispositions": ["fixed", "workaround", "escalated_bug", "unresolved"]},
    },
    {
        "id": "survey", "name": "Survey & Feedback", "icon": "clipboard", "category": "Research",
        "description": "Runs NPS/CSAT and custom surveys conversationally and records structured answers.",
        "persona": {"name": "Isha", "role": "customer feedback researcher",
                    "goals": ["Ask each survey question naturally, one at a time", "Probe briefly on low scores", "Thank the participant", "Never argue with feedback"]},
        "analysis": {"extraction": [E("nps", "number", "0-10 likelihood to recommend"), E("csat", "number", "1-5 satisfaction"), E("top_feedback", "string", "Most important feedback")],
                     "dispositions": ["completed", "partial", "declined"]},
    },
    {
        "id": "debt-collection", "name": "Payment Reminders & Collections", "icon": "banknote", "category": "Finance",
        "description": "Compliant, empathetic payment reminders with payment plans and promise-to-pay capture.",
        "persona": {"name": "Neha", "role": "accounts receivable assistant",
                    "goals": ["Verify identity before discussing any amount", "Remind about the due amount and date politely", "Offer payment options and plans", "Record a promise-to-pay date", "Never threaten, shame or harass"]},
        "analysis": {"extraction": [E("promise_to_pay_date", "string", "Date the customer committed to pay"), E("amount_committed", "number", "Amount committed"), E("hardship", "boolean", "Customer reported financial hardship")],
                     "dispositions": ["promise_to_pay", "paid", "dispute", "hardship", "refused", "wrong_person"]},
    },
    {
        "id": "appointment-reminder", "name": "Appointment Reminders", "icon": "calendar", "category": "Front desk",
        "description": "Confirms upcoming appointments, reschedules and reduces no-shows.",
        "persona": {"name": "Sara", "role": "appointment coordinator",
                    "goals": ["Confirm the appointment details", "Reschedule or cancel if needed", "Share preparation instructions from the knowledge base"]},
        "analysis": {"extraction": [E("confirmed", "boolean", "Appointment confirmed"), E("new_time", "string", "New time if rescheduled")],
                     "dispositions": ["confirmed", "rescheduled", "cancelled", "no_response"]},
    },
    {
        "id": "order-status", "name": "Order Status & Tracking", "icon": "truck", "category": "E-commerce",
        "description": "Looks up orders from your order sheet, shares status and handles returns.",
        "persona": {"name": "Zoya", "role": "order support assistant",
                    "goals": ["Ask for the order ID or registered phone number", "Look up the order with query_table", "Explain status, ETA and return/refund policy", "Escalate damaged or missing items"]},
        "analysis": {"extraction": [E("order_id", "string", "Order ID"), E("request_type", "string", "status, return, refund, cancel, other")],
                     "dispositions": ["status_shared", "return_initiated", "escalated", "order_not_found"]},
    },
    {
        "id": "customer-onboarding", "name": "Customer Onboarding", "icon": "rocket", "category": "Success",
        "description": "Welcomes new customers, walks them through setup and answers first questions.",
        "persona": {"name": "Tara", "role": "customer onboarding guide",
                    "goals": ["Welcome the customer", "Guide them through setup step by step", "Check understanding", "Book a call with success if they are stuck"]},
        "analysis": {"extraction": [E("setup_complete", "boolean", "Whether setup was completed"), E("blocker", "string", "Main blocker")],
                     "dispositions": ["onboarded", "partially_onboarded", "needs_help"]},
    },
    {
        "id": "real-estate", "name": "Real Estate Advisor", "icon": "home", "category": "Real estate",
        "description": "Answers listing questions, qualifies buyers and books site visits.",
        "persona": {"name": "Vikram", "role": "property advisor",
                    "goals": ["Understand budget, location, configuration and timeline", "Recommend matching listings from the knowledge base", "Book a site visit"]},
        "analysis": {"extraction": [E("budget", "string", "Budget"), E("location", "string", "Preferred location"), E("configuration", "string", "e.g. 2BHK"), E("site_visit", "boolean", "Site visit booked")],
                     "dispositions": ["site_visit_booked", "interested", "not_interested", "callback_requested"]},
    },
    {
        "id": "clinic", "name": "Clinic Front Desk", "icon": "stethoscope", "category": "Healthcare",
        "description": "Books doctor appointments and answers service questions. Never gives medical advice.",
        "persona": {"name": "Ananya", "role": "clinic front-desk assistant",
                    "goals": ["Book, reschedule or cancel appointments", "Answer questions about doctors, timings, fees and services", "Never diagnose or give medical advice; escalate urgent symptoms and advise emergency services"]},
        "handoff": {"topics": ["chest pain", "bleeding", "emergency", "suicide", "overdose"]},
        "analysis": {"extraction": [E("patient_name", "string", "Patient name"), E("department", "string", "Department or doctor"), E("urgent", "boolean", "Urgent symptoms mentioned")],
                     "dispositions": ["appointment_booked", "question_answered", "urgent_escalated"]},
    },
    {
        "id": "restaurant", "name": "Restaurant Host", "icon": "utensils", "category": "Hospitality",
        "description": "Takes reservations, answers menu questions and handles takeaway inquiries.",
        "persona": {"name": "Leo", "role": "restaurant host",
                    "goals": ["Take table reservations (date, time, guests, name, phone)", "Answer menu, timing and location questions", "Mention specials from the knowledge base"]},
        "analysis": {"extraction": [E("party_size", "number", "Number of guests"), E("reservation_time", "string", "Requested time")],
                     "dispositions": ["reservation_made", "question_answered", "declined"]},
    },
    {
        "id": "cod-confirmation", "name": "COD Order Confirmation", "icon": "package-check", "category": "E-commerce",
        "description": "Confirms cash-on-delivery orders and address details to cut RTO.",
        "persona": {"name": "Riya", "role": "order confirmation assistant",
                    "goals": ["Confirm the order items and amount", "Verify delivery address and landmark", "Record cancellation reasons"]},
        "analysis": {"extraction": [E("confirmed", "boolean", "Order confirmed"), E("address_changed", "boolean", "Address updated"), E("cancel_reason", "string", "Reason if cancelled")],
                     "dispositions": ["confirmed", "cancelled", "address_updated", "unreachable"]},
    },
    {
        "id": "cart-recovery", "name": "Abandoned Cart Recovery", "icon": "shopping-cart", "category": "E-commerce",
        "description": "Follows up on abandoned carts, answers objections and shares offers.",
        "persona": {"name": "Meera", "role": "shopping assistant",
                    "goals": ["Remind the customer about their cart", "Answer product questions", "Share current offers from the knowledge base", "Send a checkout link via WhatsApp or SMS"]},
        "analysis": {"extraction": [E("objection", "string", "Why they didn't buy"), E("will_purchase", "boolean", "Intends to complete purchase")],
                     "dispositions": ["recovered", "interested", "not_interested"]},
    },
    {
        "id": "recruitment", "name": "Recruitment Screening", "icon": "user-search", "category": "HR",
        "description": "Screens candidates, checks requirements and schedules interviews.",
        "persona": {"name": "Nikhil", "role": "talent acquisition coordinator",
                    "goals": ["Confirm interest in the role", "Ask screening questions (experience, notice period, CTC expectations, location)", "Schedule an interview for suitable candidates"]},
        "analysis": {"extraction": [E("experience_years", "number", "Years of experience"), E("notice_period", "string", "Notice period"), E("expected_ctc", "string", "Expected compensation"), E("suitable", "boolean", "Meets requirements")],
                     "dispositions": ["interview_scheduled", "rejected", "not_interested", "callback_requested"]},
    },
    {
        "id": "education", "name": "Admissions Counsellor", "icon": "graduation-cap", "category": "Education",
        "description": "Answers course and fee questions, qualifies students and books counselling sessions.",
        "persona": {"name": "Priya", "role": "admissions counsellor",
                    "goals": ["Understand the student's goals and background", "Recommend suitable courses", "Explain fees, scholarships and schedules", "Book a counselling session"]},
        "analysis": {"extraction": [E("course_interest", "string", "Course of interest"), E("intake", "string", "Target intake")],
                     "dispositions": ["session_booked", "interested", "not_interested"]},
    },
    {
        "id": "blank", "name": "Start from scratch", "icon": "sparkles", "category": "Custom",
        "description": "A blank agent for any purpose. Describe what it should do.",
        "persona": {"name": "Assistant", "role": "helpful assistant", "goals": []},
        "analysis": {},
    },
]

TEMPLATE_BY_ID = {t["id"]: t for t in TEMPLATES}


def template_config(template_id: str) -> dict[str, Any]:
    t = TEMPLATE_BY_ID.get(template_id) or TEMPLATE_BY_ID["blank"]
    cfg: dict[str, Any] = {"persona": dict(t["persona"])}
    if t.get("analysis"):
        cfg["analysis"] = dict(t["analysis"])
    if t.get("handoff"):
        cfg["handoff"] = dict(t["handoff"])
    return cfg
