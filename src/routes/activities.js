const express = require('express');
const router = express.Router();
const prisma = require('../db');

// GET /api/activities - Fetch call log history with recordings & transcripts
router.get('/', async (req, res) => {
  try {
    const activities = await prisma.activity.findMany({
      include: {
        lead: true,
        contact: true
      },
      orderBy: { createdAt: 'desc' }
    });

    res.json({ success: true, activities });
  } catch (error) {
    console.error('Error fetching activities:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// POST /api/activities - Log a call activity from the Python Voice Engine
router.post('/', async (req, res) => {
  try {
    const {
      leadId,
      phone,
      type,
      direction,
      durationSec,
      recordingUrl,
      transcript,
      summary,
      intent,
      accountId
    } = req.body;

    let targetAccountId = accountId;
    if (!targetAccountId) {
      const defaultAccount = await prisma.account.findFirst();
      if (!defaultAccount) {
        return res.status(400).json({ success: false, error: 'No clinic account configured' });
      }
      targetAccountId = defaultAccount.id;
    }

    let contactId = null;
    if (phone) {
      const contact = await prisma.contact.findFirst({
        where: { accountId: targetAccountId, phone }
      });
      if (contact) {
        contactId = contact.id;
      }
    }

    const activity = await prisma.activity.create({
      data: {
        accountId: targetAccountId,
        leadId: leadId || null,
        contactId,
        type: type || 'CALL',
        direction: direction || 'INBOUND',
        durationSec: durationSec || 0,
        recordingUrl: recordingUrl || null,
        transcript: transcript || '',
        summary: summary || '',
        intent: intent || 'general_query'
      }
    });

    res.status(201).json({ success: true, activity });
  } catch (error) {
    console.error('Error logging activity:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

module.exports = router;
