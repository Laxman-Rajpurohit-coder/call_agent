"""
Vobiz Webhook Server — returns XML call instructions.

When a caller dials +918065354620, Vobiz hits this URL.
We respond with XML telling Vobiz to connect the call
to our Asterisk PBX via the SIP trunk.
"""

import asyncio
from aiohttp import web

VOBIZ_SIP_DOMAIN = "a5962fe0.sip.vobiz.ai"
SIP_USERNAME = "superfone_user"

# Vobiz sends POST to this endpoint when a call comes in
async def handle_answer(request):
    # Log incoming call details
    try:
        data = await request.post()
        caller = data.get("From", "unknown")
        called = data.get("To", "unknown")
        call_sid = data.get("CallSid", "unknown")
        print(f"[Vobiz Webhook] Incoming call: {caller} -> {called} (CallSid={call_sid})")
    except Exception:
        print("[Vobiz Webhook] Incoming call (could not parse POST data)")

    # Return XML instructing Vobiz to dial our SIP trunk
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial>
        <Sip>sip:700@{VOBIZ_SIP_DOMAIN}</Sip>
    </Dial>
</Response>"""

    return web.Response(
        text=xml_response,
        content_type="application/xml",
        status=200,
    )


async def handle_hangup(request):
    try:
        data = await request.post()
        call_sid = data.get("CallSid", "unknown")
        duration = data.get("Duration", "unknown")
        print(f"[Vobiz Webhook] Call ended: CallSid={call_sid} Duration={duration}s")
    except Exception:
        print("[Vobiz Webhook] Call ended (could not parse POST data)")

    return web.Response(text="OK", status=200)


async def handle_health(request):
    return web.Response(text="Vobiz Webhook OK", status=200)


async def main():
    app = web.Application()
    app.router.add_post("/answer", handle_answer)
    app.router.add_get("/answer", handle_answer)
    app.router.add_post("/hangup", handle_hangup)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print(f"[Vobiz Webhook] Listening on http://0.0.0.0:8080/answer")
    print(f"[Vobiz Webhook] Returning SIP dial to: sip:700@{VOBIZ_SIP_DOMAIN}")

    # Run forever
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
