const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');
const cors = require('cors');
require('dotenv').config();

const prisma = require('./src/db');
const authRoutes = require('./src/routes/auth');
const leadsRoutes = require('./src/routes/leads');
const activitiesRoutes = require('./src/routes/activities');
const telephonyRoutes = require('./src/routes/telephony');

process.on('uncaughtException', (err) => {
  console.error('[Server Error] Uncaught exception:', err);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('[Server Error] Unhandled rejection:', reason);
});

process.on('uncaughtException', (err) => {
  console.error('[Server Error] Uncaught exception:', err);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('[Server Error] Unhandled rejection:', reason);
});

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST']
  }
});

const PORT = process.env.PORT || 8080;

// Middleware
app.use(cors());
app.use(express.json());
app.use((err, req, res, next) => {
  if (err instanceof SyntaxError && err.status === 400 && 'body' in err) {
    console.error('[Express Error] Handled invalid JSON payload:', err.message);
    return res.status(400).json({ success: false, error: 'Invalid JSON payload' });
  }
  next();
});
app.use(express.urlencoded({ extended: true }));

// Serve compiled React Main Dashboard (frontend/dist), legacy agent portal, and call recordings
app.use(express.static(path.join(__dirname, 'frontend/dist')));
app.use('/agent-legacy', express.static(path.join(__dirname, 'public')));
app.use('/recordings', express.static(path.join(__dirname, 'recordings')));

// API Routes
app.use('/api/auth', authRoutes);
app.use('/api/leads', leadsRoutes);
app.use('/api/activities', activitiesRoutes);
app.use('/api/telephony', telephonyRoutes);

// Tasks API (Synced with Voice Operations Database)
app.get('/api/tasks', async (req, res) => {
  try {
    const response = await fetch('http://127.0.0.1:9090/api/v1/tasks');
    const data = await response.json();
    res.json({ success: true, tasks: data });
  } catch (err) {
    res.json({ success: true, tasks: [] });
  }
});

app.patch('/api/tasks/:id', async (req, res) => {
  try {
    const response = await fetch(`http://127.0.0.1:9090/api/v1/tasks/${req.params.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    });
    const data = await response.json();
    res.json({ success: true, data });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.post('/api/telephony/originate', async (req, res) => {
  try {
    const response = await fetch('http://127.0.0.1:9090/api/v1/microsip/originate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body)
    });
    const data = await response.json();
    res.json({ success: true, data });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// ─── Exotel Outbound Scripted Call (Dashboard "Call" Button) ───────────────
// How it works:
//   From = ExoPhone (Exotel runs Flow 1337835 on this leg → Riya AI voicebot starts)
//   To   = Lead's mobile (Exotel dials them and bridges the two legs together)
// Result: Lead picks up → Riya AI is already speaking via Voicebot applet.
app.post('/api/telephony/outbound-call', async (req, res) => {
  const { to, contact_name, contact_id } = req.body;
  if (!to) return res.status(400).json({ success: false, error: 'Missing "to" phone number' });

  const accountSid  = process.env.EXOTEL_ACCOUNT_SID   || 'snazzyitsolutions1';
  const apiKey      = process.env.EXOTEL_API_KEY        || '';
  const apiToken    = process.env.EXOTEL_API_TOKEN      || '';
  const virtualNum  = process.env.EXOTEL_VIRTUAL_NUMBER || '08047283364';

  // Clean phone number — strip spaces, convert +91XXXXXXXXXX → 0XXXXXXXXXX
  const cleanTo = to.replace(/\s+/g, '').replace(/^\+91/, '0');

  try {
    const exotelUrl = `https://api.exotel.com/v1/Accounts/${accountSid}/Calls/connect.json`;
    const params = new URLSearchParams({
      From:           cleanTo,      // Lead's mobile — Exotel calls them first
      To:             virtualNum,   // ExoPhone — bridged after lead picks up
      CallerId:       virtualNum,   // CLI shown on lead's phone
      // Our /voice webhook returns Exotel Voicebot ExoML → triggers Riya AI
      Url:            `https://drool-envoy-sandy.ngrok-free.dev/voice`,
      StatusCallback: `https://drool-envoy-sandy.ngrok-free.dev/api/telephony/webhook`,
      CallType:       'trans',
      TimeLimit:      '3600',
      TimeOut:        '30',
    });

    const credentials = Buffer.from(`${apiKey}:${apiToken}`).toString('base64');
    const response = await fetch(exotelUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Basic ${credentials}`,
        'Content-Type':  'application/x-www-form-urlencoded',
      },
      body: params.toString()
    });

    const data = await response.json();
    console.log(`[Exotel Outbound Call] Triggered call to ${cleanTo}:`, JSON.stringify(data, null, 2));

    if (response.ok) {
      const callSid = data?.Call?.Sid || data?.call_sid || 'unknown';
      res.json({ success: true, call_sid: callSid, to: cleanTo, message: `Outbound AI call initiated to ${cleanTo}` });
    } else {
      res.status(response.status).json({ success: false, error: data?.RestException?.Message || 'Exotel API error', raw: data });
    }
  } catch (err) {
    console.error('[Outbound Call] Error:', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});
// ───────────────────────────────────────────────────────────────────────────



// Seed default clinic account and admin user if DB is empty
async function seedDefaultData() {
  try {
    let account = await prisma.account.findFirst();
    if (!account) {
      account = await prisma.account.create({
        data: {
          name: 'Smile Dental Clinic',
          phone: '+91-9876543210',
          workingHours: '09:00 AM - 08:00 PM',
          agentName: 'Riya AI Receptionist',
          voiceName: 'Deepgram Aura Aditi'
        }
      });
      console.log(`[Seed] Created default clinic account: ${account.name} (${account.id})`);
    }

    const admin = await prisma.user.findFirst({ where: { email: 'admin@smiledental.com' } });
    if (!admin) {
      await prisma.user.create({
        data: {
          accountId: account.id,
          name: 'Dr. Sharma (Admin)',
          email: 'admin@smiledental.com',
          password: 'admin123',
          role: 'ADMIN'
        }
      });
      console.log(`[Seed] Created default admin user: admin@smiledental.com / admin123`);
    }

    const agent = await prisma.user.findFirst({ where: { email: 'agent@smiledental.com' } });
    if (!agent) {
      await prisma.user.create({
        data: {
          accountId: account.id,
          name: 'Agent Vikas',
          email: 'agent@smiledental.com',
          password: 'agent123',
          role: 'AGENT'
        }
      });
      console.log(`[Seed] Created default agent user: agent@smiledental.com / agent123`);
    }
  } catch (err) {
    console.log('[Seed] DB initialization warning:', err.message);
  }
}

// Store active WebRTC rooms and participants
const rooms = new Map();

io.on('connection', (socket) => {
  console.log(`[Socket] User connected: ${socket.id}`);

  // Join a voice call room
  socket.on('join-room', (roomId) => {
    socket.join(roomId);
    
    if (!rooms.has(roomId)) {
      rooms.set(roomId, new Set());
    }
    rooms.get(roomId).add(socket.id);
    
    const otherUsers = Array.from(rooms.get(roomId)).filter(id => id !== socket.id);
    socket.emit('all-users', otherUsers);

    console.log(`[Socket] User ${socket.id} joined room ${roomId}. Total users: ${rooms.get(roomId).size}`);
  });

  // Relay WebRTC SDP offer
  socket.on('offer', ({ target, sdps }) => {
    io.to(target).emit('offer', {
      caller: socket.id,
      sdps
    });
  });

  // Relay WebRTC SDP answer
  socket.on('answer', ({ target, sdps }) => {
    io.to(target).emit('answer', {
      responder: socket.id,
      sdps
    });
  });

  // Relay ICE candidate
  socket.on('ice-candidate', ({ target, candidate }) => {
    io.to(target).emit('ice-candidate', {
      sender: socket.id,
      candidate
    });
  });

  // Screen Pop Event trigger for human warm handoff
  socket.on('trigger-handoff-pop', (payload) => {
    console.log('[Socket] Broadcasting Human Handoff Screen Pop Payload:', payload);
    io.emit('screen-pop-handoff', payload);
  });

  // Toggle Mute notification
  socket.on('toggle-audio', ({ roomId, muted }) => {
    socket.to(roomId).emit('user-audio-toggle', {
      userId: socket.id,
      muted
    });
  });

  // Leave room / disconnect
  socket.on('disconnecting', () => {
    socket.rooms.forEach(roomId => {
      if (rooms.has(roomId)) {
        rooms.get(roomId).delete(socket.id);
        if (rooms.get(roomId).size === 0) {
          rooms.delete(roomId);
        } else {
          socket.to(roomId).emit('user-left', socket.id);
        }
      }
    });
  });

  socket.on('disconnect', () => {
    console.log(`[Socket] User disconnected: ${socket.id}`);
  });
});

// Native WebSocket Media Stream Server for Exotel & CPaaS Telephony
const WebSocket = require('ws');
const wss = new WebSocket.Server({ noServer: true });

server.on('upgrade', (request, socket, head) => {
  const pathname = request.url ? request.url.split('?')[0] : '';
  if (pathname === '/media-stream' || pathname === '/media' || pathname === '/api/telephony/webhook') {
    wss.handleUpgrade(request, socket, head, (ws) => {
      wss.emit('connection', ws, request);
    });
  }
});

wss.on('connection', (clientWs, req) => {
  console.log(`[Telephony Proxy] 🚀 New Exotel WebSocket Stream Connection from ${req.socket.remoteAddress}`);
  
  // Notify Dashboard via Socket.IO
  io.emit('screen-pop-handoff', {
    name: 'Laxman Singh',
    phone: '08830718466',
    need: 'AI Voice Receptionist',
    preferredTime: 'Live Active Call',
    status: 'in_progress',
    message: 'Exotel Voice Stream Connected'
  });

  // Connect to Python Neural AI Voice Engine (trying port 9096, fallback to 9097)
  let targetWs = new WebSocket('ws://127.0.0.1:9096/media-stream');
  const pendingBuffer = [];

  const setupTargetHandlers = (wsInst) => {
    wsInst.on('open', () => {
      console.log('[Telephony Proxy] ✅ Stream connected to Python AI Voice Engine!');
      // Flush any early messages (e.g. start event) received while connecting
      while (pendingBuffer.length > 0) {
        const item = pendingBuffer.shift();
        if (wsInst.readyState === WebSocket.OPEN) {
          if (item.msgStr !== null) {
            wsInst.send(item.msgStr, { binary: false });
          } else {
            wsInst.send(item.msg, { binary: item.isBinary });
          }
        }
      }
    });

    wsInst.on('message', (msg, isBinary) => {
      if (clientWs.readyState === WebSocket.OPEN) {
        let msgStr = null;
        if (typeof msg === 'string') {
          msgStr = msg;
        } else if (Buffer.isBuffer(msg) && msg.length > 0 && msg[0] === 123) {
          msgStr = msg.toString('utf8');
        }

        if (msgStr !== null) {
          clientWs.send(msgStr, { binary: false });
        } else {
          clientWs.send(msg, { binary: isBinary });
        }
      }
    });

    wsInst.on('close', () => {
      if (clientWs.readyState === WebSocket.OPEN) clientWs.close();
    });

    wsInst.on('error', (err) => {
      console.error('[Telephony Proxy] ⚠️ Target Engine Error:', err.message);
      if (clientWs.readyState === WebSocket.OPEN && wsInst === targetWs) {
        console.log('[Telephony Proxy] 🔄 Retrying connection on fallback port 9097...');
        targetWs = new WebSocket('ws://127.0.0.1:9097/media-stream');
        setupTargetHandlers(targetWs);
      }
    });
  };

  setupTargetHandlers(targetWs);

  // Exotel -> Python AI Engine (Preserve opcode type & buffer early frames)
  clientWs.on('message', (msg, isBinary) => {
    let msgStr = null;
    if (typeof msg === 'string') {
      msgStr = msg;
    } else if (Buffer.isBuffer(msg) && msg.length > 0 && msg[0] === 123) {
      msgStr = msg.toString('utf8');
    }

    if (targetWs.readyState === WebSocket.OPEN) {
      if (msgStr !== null) {
        targetWs.send(msgStr, { binary: false });
      } else {
        targetWs.send(msg, { binary: isBinary });
      }
    } else if (targetWs.readyState === WebSocket.CONNECTING) {
      pendingBuffer.push({ msg, msgStr, isBinary });
    }
  });

  clientWs.on('close', () => {
    console.log('[Telephony Proxy] 🛑 Exotel Stream Closed');
    if (targetWs.readyState === WebSocket.OPEN) targetWs.close();
    io.emit('call-ended', { caller: '08830718466' });
  });

  clientWs.on('error', (err) => {
    console.error('[Telephony Proxy] ⚠️ Client Stream Error:', err.message);
    if (targetWs.readyState === WebSocket.OPEN) targetWs.close();
  });

});

// SPA Fallback: Serve full Superfone AI React Dashboard index.html for client routes
app.get('*', (req, res, next) => {
  if (req.url.startsWith('/api') || req.url.startsWith('/recordings') || req.url.startsWith('/media')) {
    return next();
  }
  res.sendFile(path.join(__dirname, 'frontend/dist', 'index.html'));
});


server.listen(PORT, '0.0.0.0', async () => {
  await seedDefaultData();
  console.log(`====================================================`);
  console.log(`🚀 Voice Agent & CRM Server running on http://localhost:${PORT}`);
  console.log(`====================================================`);
});

