const express = require('express');
const router = express.Router();
const prisma = require('../db');

// POST /api/auth/login - Admin/Agent login endpoint
router.post('/login', async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password) {
      return res.status(400).json({ success: false, error: 'Email and password are required' });
    }

    const user = await prisma.user.findUnique({
      where: { email },
      include: { account: true }
    });

    if (!user || user.password !== password) {
      return res.status(401).json({ success: false, error: 'Invalid email or password' });
    }

    res.json({
      success: true,
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
        role: user.role,
        account: user.account
      },
      token: `demo-token-${user.id}`
    });
  } catch (error) {
    console.error('Error during auth login:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

module.exports = router;
