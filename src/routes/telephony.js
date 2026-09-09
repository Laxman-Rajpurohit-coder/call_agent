const express = require('express');
const router = express.Router();
const prisma = require('../db');

// POST/GET /api/telephony/webhook - Unified Webhook receiver for CPaaS (Exotel Stream / Twilio / SIP)
const handleWebhook = async (req, res) => {
  try {
    const { From, To, CallSid, CallStatus } = { ...req.query, ...req.body };
    console.log(`[Telephony Webhook] Call Event received: From=${From}, To=${To}, Status=${CallStatus || 'active'}`);

    const host = req.headers.host || 'drool-envoy-sandy.ngrok-free.dev';
    const wsScheme = (req.secure || host.includes('ngrok')) ? 'wss' : 'ws';
    const streamUrl = `${wsScheme}://${host}/media-stream`;

    // Exotel Stream Applet returns JSON wss URL if requested or format=json
    if (req.headers.accept?.includes('application/json') || req.query.format === 'json') {
      return res.json({ url: streamUrl, status: 'success' });
    }

    // Standard TWIML / CPaaS Response to connect inbound call stream
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

    const authHeader = 'Basic ' + Buffer.from(`${apiKey}:${apiToken}`).toString('base64');
    const exotelUrl = `https://api.exotel.com/v1/Accounts/${accountSid}/Calls/connect.json`;

    const webhookUrl = `https://${req.headers.host || 'drool-envoy-sandy.ngrok-free.dev'}/api/telephony/webhook`;
    const params = new URLSearchParams({
      From: to,
      To: to,
      CallerId: callerId,
      Url: webhookUrl,
      CallType: 'trans'
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
    console.log(`[Exotel Outbound Call] Triggered call to ${to}:`, data);
    res.json({ success: true, data });
  } catch (err) {
    console.error('[Exotel Outbound Call Error]:', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

module.exports = router;

