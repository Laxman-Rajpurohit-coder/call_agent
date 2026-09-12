const express = require('express');
const router = express.Router();
const prisma = require('../db');

// POST/GET /api/telephony/webhook - Unified Webhook receiver for CPaaS (Exotel Stream / Twilio / SIP)
const handleWebhook = async (req, res) => {
  try {
    const { From, To, CallSid, CallStatus } = { ...req.query, ...req.body };
    console.log(`[Telephony Webhook] 📥 Call Event: Method=${req.method}, From=${From}, To=${To}, Status=${CallStatus || 'active'}`);
    console.log(`[Telephony Webhook] Headers: User-Agent=${req.headers['user-agent']}, Accept=${req.headers['accept']}`);
    console.log(`[Telephony Webhook] Query:`, JSON.stringify(req.query));
    console.log(`[Telephony Webhook] Body:`, JSON.stringify(req.body));

    const host = req.headers.host || 'drool-envoy-sandy.ngrok-free.dev';
    const wsScheme = (req.secure || host.includes('ngrok')) ? 'wss' : 'ws';
    const streamUrl = `${wsScheme}://${host}/media-stream`;

    // Exotel Stream Applet returns JSON wss URL if requested or format=json or Exotel Passthru
    if (req.headers.accept?.includes('application/json') || req.query.format === 'json') {
      console.log(`[Telephony Webhook] ⏩ Returning JSON Stream URL: ${streamUrl}`);
      return res.json({ url: streamUrl, select: 'stream', status: 'success' });
    }

    console.log(`[Telephony Webhook] ⏩ Returning XML Stream Response: ${streamUrl}`);
    return res.type('text/xml').send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="${streamUrl}" />
    </Connect>
</Response>`);
  } catch (error) {
    console.error('Error handling telephony webhook:', error);
    res.status(500).type('text/xml').send(`<?xml version="1.0" encoding="UTF-8"?><Response><Say>An error occurred connecting your call.</Say></Response>`);
  }
};

router.get('/webhook', handleWebhook);
router.post('/webhook', handleWebhook);

// POST /api/telephony/outbound-call - Trigger automated outbound AI call via Exotel API
router.post('/outbound-call', async (req, res) => {
  try {
    const to = req.body?.to || req.query?.to;
    if (!to) {
      return res.status(400).json({ success: false, error: 'Recipient phone number (to) is required.' });
    }


    const accountSid = process.env.EXOTEL_ACCOUNT_SID || 'snazzyitsolutions1';
    const apiKey = process.env.EXOTEL_API_KEY;
    const apiToken = process.env.EXOTEL_API_TOKEN;
    const callerId = process.env.EXOTEL_VIRTUAL_NUMBER || '08047283364';

    if (!apiKey || !apiToken) {
      return res.status(500).json({ success: false, error: 'Exotel API key or token missing in .env' });
    }

    const cleanTo = to.replace(/\s+/g, '').replace(/^\+91/, '0');
    const authHeader = 'Basic ' + Buffer.from(`${apiKey}:${apiToken}`).toString('base64');
    const exotelUrl = `https://api.exotel.com/v1/Accounts/${accountSid}/Calls/connect.json`;

    // Exact Exotel Flow URL for Voicebot flow (Flow 1337835 attached to ExoPhone 08047283364)
    const flowUrl = `https://my.exotel.com/${accountSid}/exoml/start_voice/1337835`;
    const params = new URLSearchParams({
      From: cleanTo,
      To: callerId,
      CallerId: callerId,
      Url: flowUrl,
      CallType: 'trans',
      TimeLimit: '3600',
      TimeOut: '30'
    });

    const exotelRes = await fetch(exotelUrl, {
      method: 'POST',
      headers: {
        'Authorization': authHeader,
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: params.toString()
    });

    const data = await exotelRes.json();
    console.log(`[Exotel Outbound Call] Triggered call to ${cleanTo} via Flow ${flowUrl}:`, data);
    res.json({ success: true, data });
  } catch (err) {
    console.error('[Exotel Outbound Call Error]:', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;

