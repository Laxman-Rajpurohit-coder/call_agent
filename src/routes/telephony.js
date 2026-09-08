const express = require('express');
const router = express.Router();
const prisma = require('../db');

// POST /api/telephony/webhook - Unified Webhook receiver for CPaaS (Exotel / Twilio / SIP Trunk)
router.post('/webhook', async (req, res) => {
  try {
    const { From, To, CallSid, CallStatus, Duration } = req.body;
    console.log(`[Telephony Webhook] Call Event received: From=${From}, Status=${CallStatus}`);

    // Standard TWIML / CPaaS Response to connect inbound call stream to Python Voice Engine
    if (CallStatus === 'ringing' || CallStatus === 'initiated' || req.query.event === 'incoming') {
      return res.type('text/xml').send(`<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Aditi">Thank you for calling Smile Dental Clinic. Connecting you to Riya, your AI Assistant.</Say>
    <Connect>
        <Stream url="wss://${req.headers.host}/media-stream" />
    </Connect>
</Response>`);
    }

    res.json({ success: true, message: 'Webhook event processed' });
  } catch (error) {
    console.error('Error handling telephony webhook:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

module.exports = router;
