const express = require('express');
const router = express.Router();
const prisma = require('../db');

// GET /api/leads - List all leads with optional filtering
router.get('/', async (req, res) => {
  try {
    const { status, search } = req.query;
    const where = {};

    if (status) {
      where.status = status;
    }

    if (search) {
      where.OR = [
        { name: { contains: search } },
        { phone: { contains: search } },
        { need: { contains: search } }
      ];
    }

    const leads = await prisma.lead.findMany({
      where,
      include: {
        activities: {
          orderBy: { createdAt: 'desc' },
          take: 5
        }
      },
      orderBy: { createdAt: 'desc' }
    });

    res.json({ success: true, leads });
  } catch (error) {
    console.error('Error fetching leads:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// POST /api/leads - Create a new lead (from AI Voice Agent or Web UI)
router.post('/', async (req, res) => {
  try {
    const { name, phone, need, preferredTime, source, accountId } = req.body;

    if (!name || !phone) {
      return res.status(400).json({ success: false, error: 'Name and phone are required' });
    }

    // Get default clinic account if not passed
    let targetAccountId = accountId;
    if (!targetAccountId) {
      const defaultAccount = await prisma.account.findFirst();
      if (!defaultAccount) {
        return res.status(400).json({ success: false, error: 'No clinic account configured' });
      }
      targetAccountId = defaultAccount.id;
    }

    // Upsert Contact record
    const contact = await prisma.contact.upsert({
      where: {
        accountId_phone: {
          accountId: targetAccountId,
          phone
        }
      },
      update: { name },
      create: {
        accountId: targetAccountId,
        name,
        phone
      }
    });

    // Create Lead record
    const lead = await prisma.lead.create({
      data: {
        accountId: targetAccountId,
        contactId: contact.id,
        name,
        phone,
        need: need || 'General Inquiry',
        preferredTime: preferredTime || 'Flexible',
        status: 'NEW',
        source: source || 'INBOUND_AI_CALL'
      }
    });

    res.status(201).json({ success: true, lead });
  } catch (error) {
    console.error('Error creating lead:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// PATCH /api/leads/:id - Update lead status or details
router.patch('/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { status, name, need, preferredTime } = req.body;

    const updatedLead = await prisma.lead.update({
      where: { id },
      data: {
        ...(status && { status }),
        ...(name && { name }),
        ...(need && { need }),
        ...(preferredTime && { preferredTime })
      }
    });

    res.json({ success: true, lead: updatedLead });
  } catch (error) {
    console.error('Error updating lead:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

module.exports = router;
