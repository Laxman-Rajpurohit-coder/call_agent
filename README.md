# WebRTC Voice Calling Agent Structure

A modern real-time WebRTC audio calling structure with Node.js Express & Socket.io signaling server.

## Features
- **Real-Time Voice Streaming**: Ultra-low latency WebRTC peer-to-peer audio connections.
- **Node.js & Socket.io Signaling**: Room-based signaling server (`server.js`) for SDP offer/answer exchange and ICE candidate relay.
- **Audio Visualizer**: Dynamic HTML5 Canvas audio spectrum visualization.
- **Call Controls**: Mute/Unmute toggle, participant list, call duration timer, and hangup.
- **Modern UI**: Dark glassmorphic responsive interface.

## Quick Start

### 1. Install Dependencies
```bash
npm install
```

### 2. Run Signaling & App Server
```bash
npm run dev
```

### 3. Open in Browser
Navigate to `http://localhost:3000` in multiple browser tabs or devices, enter the same Room ID (e.g. `demo-room`), and click **Join Voice Room**.

## Project Architecture
- `server.js` - Express server with Socket.io signaling handlers for WebRTC mesh topology.
- `public/index.html` - Application user interface.
- `public/style.css` - Custom styling tokens and animations.
- `public/app.js` - Client-side WebRTC logic, stream handling, and Web Audio API spectrum visualizer.
