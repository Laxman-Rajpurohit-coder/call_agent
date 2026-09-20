const fs = require('fs');
const path = require('path');

const DB_FILE = path.join(__dirname, '../data/db.json');

function ensureDbFile() {
  const dir = path.dirname(DB_FILE);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  if (!fs.existsSync(DB_FILE)) {
    const initialData = {
      accounts: [],
      users: [],
      contacts: [],
      leads: [],
      activities: [],
      appointments: []
    };
    fs.writeFileSync(DB_FILE, JSON.stringify(initialData, null, 2), 'utf8');
  }
}

function readDb() {
  ensureDbFile();
  try {
    const raw = fs.readFileSync(DB_FILE, 'utf8');
    return JSON.parse(raw);
  } catch (e) {
    return { accounts: [], users: [], contacts: [], leads: [], activities: [], appointments: [] };
  }
}

function writeDb(data) {
  ensureDbFile();
  fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf8');
}

function generateId() {
  return 'id_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now();
}

const db = {
  account: {
    findFirst: async () => {
      const data = readDb();
      return data.accounts[0] || null;
    },
    create: async ({ data }) => {
      const store = readDb();
      const newAccount = {
        id: generateId(),
        name: data.name,
        phone: data.phone || null,
        workingHours: data.workingHours || '09:00 AM - 08:00 PM',
        agentName: data.agentName || 'Riya AI Receptionist',
        voiceName: data.voiceName || 'Deepgram Aura Aditi',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      store.accounts.push(newAccount);
      writeDb(store);
      return newAccount;
    }
  },
  user: {
    findFirst: async ({ where } = {}) => {
      const data = readDb();
      if (!where) return data.users[0] || null;
      return data.users.find(u => (where.email ? u.email === where.email : true)) || null;
    },
    findUnique: async ({ where }) => {
      const data = readDb();
      return data.users.find(u => u.email === where.email) || null;
    },
    create: async ({ data }) => {
      const store = readDb();
      const newUser = {
        id: generateId(),
        accountId: data.accountId,
        name: data.name,
        email: data.email,
        password: data.password,
        role: data.role || 'AGENT',
        createdAt: new Date().toISOString()
      };
      store.users.push(newUser);
      writeDb(store);
      return newUser;
    }
  },
  contact: {
    findFirst: async ({ where }) => {
      const data = readDb();
      return data.contacts.find(c => c.phone === where.phone) || null;
    },
    upsert: async ({ where, update, create }) => {
      const store = readDb();
      const idx = store.contacts.findIndex(c => c.phone === create.phone);
      if (idx !== -1) {
        store.contacts[idx] = { ...store.contacts[idx], ...update, updatedAt: new Date().toISOString() };
        writeDb(store);
        return store.contacts[idx];
      } else {
        const newContact = {
          id: generateId(),
          accountId: create.accountId,
          name: create.name,
          phone: create.phone,
          email: create.email || null,
          city: create.city || null,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        };
        store.contacts.push(newContact);
        writeDb(store);
        return newContact;
      }
    }
  },
  lead: {
    findMany: async ({ where = {}, orderBy } = {}) => {
      const data = readDb();
      let list = [...data.leads];
      if (where.status) {
        list = list.filter(l => l.status === where.status);
      }
      if (where.OR) {
        const q = where.OR[0]?.name?.contains?.toLowerCase() || '';
        if (q) {
          list = list.filter(l =>
            l.name.toLowerCase().includes(q) ||
            l.phone.toLowerCase().includes(q) ||
            l.need.toLowerCase().includes(q)
          );
        }
      }
      list.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
      return list;
    },
    create: async ({ data }) => {
      const store = readDb();
      const newLead = {
        id: generateId(),
        accountId: data.accountId,
        contactId: data.contactId || null,
        name: data.name,
        phone: data.phone,
        need: data.need,
        preferredTime: data.preferredTime || 'Flexible',
        status: data.status || 'NEW',
        source: data.source || 'INBOUND_AI_CALL',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      store.leads.unshift(newLead);
      writeDb(store);
      return newLead;
    },
    update: async ({ where, data }) => {
      const store = readDb();
      const idx = store.leads.findIndex(l => l.id === where.id);
      if (idx !== -1) {
        store.leads[idx] = { ...store.leads[idx], ...data, updatedAt: new Date().toISOString() };
        writeDb(store);
        return store.leads[idx];
      }
      throw new Error('Lead not found');
    }
  },
  activity: {
    findMany: async () => {
      const data = readDb();
      const list = [...data.activities];
      list.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
      return list;
    },
    create: async ({ data }) => {
      const store = readDb();
      const newActivity = {
        id: generateId(),
        accountId: data.accountId,
        leadId: data.leadId || null,
        contactId: data.contactId || null,
        type: data.type || 'CALL',
        direction: data.direction || 'INBOUND',
        durationSec: data.durationSec || 0,
        recordingUrl: data.recordingUrl || null,
        transcript: data.transcript || '',
        summary: data.summary || '',
        intent: data.intent || 'general_query',
        createdAt: new Date().toISOString()
      };
      store.activities.unshift(newActivity);
      writeDb(store);
      return newActivity;
    }
  }
};

module.exports = db;
