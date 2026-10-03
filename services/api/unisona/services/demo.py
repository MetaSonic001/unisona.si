"""Demo data for dev mode and evals: two realistic agents with knowledge, tables and test suites."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..brain.respond import index_golden
from ..brain.templates import template_config
from ..brain.agent_config import deep_merge
from ..db import new_id
from ..knowledge.files import save_upload
from ..log import get_logger
from ..models import Agent, AgentKnowledge, Channel, EvalSuite, GoldenAnswer, KnowledgeBase, KnowledgeSource, Workspace
from ..worker.queue import enqueue

log = get_logger("demo")

DENTAL_DOC = """# BrightSmile Dental Clinic — Patient Information

## About us
BrightSmile Dental Clinic is a family dental clinic in Indiranagar, Bengaluru, founded in 2012. Address: 42, 12th Main Road, HAL 2nd Stage, Indiranagar, Bengaluru 560038. Phone: +91 80 4567 8910. Email: care@brightsmile.example.

## Opening hours
Monday to Friday: 9:00 AM to 8:00 PM. Saturday: 9:00 AM to 2:00 PM. Sunday: closed (emergency line only).
Emergency line (24x7): +91 98450 11122.

## Doctors
- Dr. Ananya Rao (BDS, MDS Orthodontics): braces, aligners. Available Mon, Wed, Fri.
- Dr. Vikram Shetty (BDS, MDS Endodontics): root canal treatment. Available Tue, Thu, Sat.
- Dr. Meera Iyer (BDS): general dentistry, cleaning, fillings, children's dentistry. Available Monday to Saturday.

## Treatments and prices (INR)
- Consultation: ₹500 (waived if treatment is started the same day)
- Scaling and polishing (cleaning): ₹1,500
- Tooth-coloured filling: ₹1,200 to ₹2,500 per tooth
- Root canal treatment (RCT): ₹6,000 to ₹9,000 depending on the tooth; crown extra
- Zirconia crown: ₹12,000 per tooth. Metal-ceramic crown: ₹6,500 per tooth.
- Teeth whitening (in-clinic): ₹8,000
- Clear aligners: from ₹1,20,000 for a full course. Metal braces: from ₹45,000.
- Wisdom tooth extraction: ₹3,500 to ₹8,000 (surgical extraction costs more).
- Dental implant: from ₹35,000 per implant including the crown.

## Payments and insurance
We accept UPI, all major cards, and cash. No-cost EMI is available on treatments above ₹20,000 through Bajaj Finserv.
We are a cashless network provider for Star Health and HDFC ERGO dental add-on plans. For other insurers we provide receipts for reimbursement.

## Appointments and cancellation policy
Appointments can be booked by phone, WhatsApp, or on our website. Please arrive 10 minutes early for your first visit.
Cancellations or reschedules are free up to 4 hours before the appointment. Late cancellations may incur a ₹300 fee.

## After a root canal
Avoid chewing on the treated side until the crown is placed. Mild discomfort for 2-3 days is normal; take the prescribed painkillers. If swelling increases or you have fever, call the emergency line.

## Children
Dr. Meera Iyer sees children from age 3. First dental visit for children is free of charge.

## Parking
Free parking for 6 cars is available in the building basement. Street parking on 12th Main is also available.

## हिंदी में जानकारी
क्लिनिक सोमवार से शुक्रवार सुबह 9 बजे से रात 8 बजे तक और शनिवार सुबह 9 बजे से दोपहर 2 बजे तक खुला रहता है। रविवार को क्लिनिक बंद रहता है।
परामर्श शुल्क ₹500 है। दांतों की सफाई (स्केलिंग) ₹1,500 में होती है।
"""

ORDERS_CSV = """order_id,customer_name,phone,status,eta,amount_inr,items,courier
SK10231,Rahul Sharma,+919876543210,shipped,2026-10-05,2499,Wireless earbuds,Delhivery
SK10232,Priya Nair,+919812345678,delivered,2026-10-01,799,Phone case,Blue Dart
SK10233,Amit Verma,+919900112233,processing,2026-10-07,15999,Smartwatch Pro,Delhivery
SK10234,Sneha Kulkarni,+919845098450,out_for_delivery,2026-10-03,1299,Yoga mat,Ekart
SK10235,Arjun Mehta,+919988776655,cancelled,,3499,Bluetooth speaker,
SK10236,Fatima Khan,+919123456789,return_initiated,2026-10-09,4599,Running shoes,Delhivery
"""

SHOP_POLICY = """# ShopKart Help Centre

## Delivery
Standard delivery takes 3-6 business days in metro cities and 5-9 days elsewhere. Express delivery (1-2 days) costs ₹99 in 40 cities.
Orders above ₹499 ship free.

## Returns and refunds
Most items can be returned within 7 days of delivery if unused and in original packaging. Electronics can be returned within 7 days only if defective or damaged.
Refunds go to the original payment method within 5-7 business days after the return is picked up. Cash-on-delivery refunds go to your ShopKart wallet or bank account (NEFT).

## Cancellation
Orders can be cancelled free of charge before they are shipped. After shipping, refuse the delivery or request a return.

## Cash on delivery
COD is available for orders up to ₹10,000. A ₹49 COD handling fee applies.

## Contact
Support hours: 8 AM to 10 PM, all days. Email support@shopkart.example.
"""

DENTAL_QA = [
    {"input": "What are your opening hours on Saturday?", "expected": "Saturday 9:00 AM to 2:00 PM.", "must_contain": ["2"]},
    {"input": "How much does a root canal cost?", "expected": "Root canal treatment costs ₹6,000 to ₹9,000 depending on the tooth, crown extra."},
    {"input": "Do you take Star Health insurance?", "expected": "Yes, cashless network provider for Star Health dental add-on plans."},
    {"input": "Which doctor does braces and when is she available?", "expected": "Dr. Ananya Rao, orthodontist, available Mon, Wed, Fri."},
    {"input": "Is there parking?", "expected": "Free basement parking for 6 cars; street parking on 12th Main also available."},
    {"input": "रविवार को क्लिनिक खुला है क्या?", "expected": "रविवार को क्लिनिक बंद रहता है; emergency line available."},
    {"input": "Do you offer laser hair removal?", "expected": "", "must_not_contain": ["₹"]},
    {"input": "Can I cancel my appointment an hour before?", "expected": "Free up to 4 hours before; late cancellations may incur a ₹300 fee."},
]
SHOP_QA = [
    {"input": "Where is my order SK10231?", "expected": "Order SK10231 (Wireless earbuds) is shipped via Delhivery, expected 2026-10-05."},
    {"input": "What is the status of order SK10235?", "expected": "Order SK10235 was cancelled."},
    {"input": "How long do refunds take?", "expected": "5-7 business days after return pickup, to the original payment method."},
    {"input": "Is COD available for a ₹12,000 order?", "expected": "No, COD only for orders up to ₹10,000."},
]


async def seed_demo(db: AsyncSession, ws: Workspace) -> dict:
    existing = (await db.execute(select(Agent).where(Agent.workspace_id == ws.id, Agent.name.in_(["Maya · BrightSmile Dental", "Zoya · ShopKart Support"])))).scalars().all()
    if existing:
        return {"agents": [a.id for a in existing], "created": False}

    async def make_agent(name: str, template: str, cfg_override: dict, kb_name: str) -> tuple[Agent, KnowledgeBase]:
        kb = KnowledgeBase(workspace_id=ws.id, name=kb_name)
        db.add(kb)
        await db.flush()
        cfg = deep_merge(template_config(template), cfg_override)
        a = Agent(workspace_id=ws.id, name=name, template_id=template, config=cfg, status="live")
        db.add(a)
        await db.flush()
        db.add(AgentKnowledge(agent_id=a.id, kb_id=kb.id, workspace_id=ws.id))
        for ch in ("web", "widget", "voice"):
            db.add(Channel(workspace_id=ws.id, agent_id=a.id, type=ch, name=ch.title()))
        return a, kb

    dental, dkb = await make_agent("Maya · BrightSmile Dental", "clinic", {
        "persona": {"name": "Maya", "role": "front-desk assistant", "tone": 70,
                    "greeting": "Hi! I'm Maya from BrightSmile Dental. How can I help you today?"},
        "business": {"name": "BrightSmile Dental Clinic", "description": "Family dental clinic in Indiranagar, Bengaluru.", "hours": "Mon-Fri 9AM-8PM, Sat 9AM-2PM",
                     "phone": "+91 80 4567 8910", "website": "https://brightsmile.example"},
        "languages": {"primary": "en-IN", "supported": ["en-IN", "hi-IN", "kn-IN", "ta-IN"]},
        "voice": {"voice_id": "edge:en-IN-NeerjaExpressiveNeural", "per_language": {"hi-IN": "edge:hi-IN-SwaraNeural", "kn-IN": "edge:kn-IN-SapnaNeural"}},
    }, "BrightSmile knowledge")
    shop, skb = await make_agent("Zoya · ShopKart Support", "order-status", {
        "persona": {"name": "Zoya", "role": "order support assistant", "tone": 65,
                    "greeting": "Hi, I'm Zoya from ShopKart! Share your order ID and I'll check it for you."},
        "business": {"name": "ShopKart", "description": "Online store for electronics, fashion and fitness.", "hours": "8 AM to 10 PM daily"},
        "voice": {"voice_id": "edge:en-IN-NeerjaExpressiveNeural"},
    }, "ShopKart help centre")
    await db.flush()
    dental.published_config = dental.config
    dental.published_version = 1
    shop.published_config = shop.config
    shop.published_version = 1

    srcs = [KnowledgeSource(workspace_id=ws.id, kb_id=dkb.id, type="text", title="BrightSmile patient information", meta={"text": DENTAL_DOC}),
            KnowledgeSource(workspace_id=ws.id, kb_id=skb.id, type="text", title="ShopKart help centre", meta={"text": SHOP_POLICY})]
    orders_id = new_id("src")
    save_upload(ws.id, orders_id, ORDERS_CSV.encode())
    srcs.append(KnowledgeSource(id=orders_id, workspace_id=ws.id, kb_id=skb.id, type="table", title="orders.csv", uri="orders.csv",
                                meta={"filename": "orders.csv"}))
    db.add_all(srcs)
    goldens = [GoldenAnswer(workspace_id=ws.id, agent_id=dental.id, question="Is the first visit free for kids?",
                            answer="Yes! The first dental visit for children is free, and Dr. Meera Iyer sees children from age 3.", source="demo"),
               GoldenAnswer(workspace_id=ws.id, agent_id=dental.id, question="Do you have EMI?",
                            answer="Yes, no-cost EMI is available on treatments above ₹20,000 through Bajaj Finserv.", source="demo")]
    db.add_all(goldens)
    db.add(EvalSuite(workspace_id=ws.id, agent_id=dental.id, name="BrightSmile FAQ accuracy", kind="qa", cases=DENTAL_QA))
    db.add(EvalSuite(workspace_id=ws.id, agent_id=shop.id, name="ShopKart order lookup", kind="qa", cases=SHOP_QA))
    await db.commit()
    for g in goldens:
        await index_golden(db, g)
    for s in srcs:
        await enqueue("knowledge.ingest", {"source_id": s.id}, workspace_id=ws.id)
    log.info(f"Seeded demo agents in {ws.id}")
    return {"agents": [dental.id, shop.id], "created": True}
