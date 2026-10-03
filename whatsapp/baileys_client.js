/**
 * whatsapp/baileys_client.js
 * 
 * Baileys WhatsApp client connector for WhatsApp Cruise Control.
 * Connects to WhatsApp Web socket, listens for incoming real-time messages,
 * extracts metadata, checks kill switch and dynamic settings, routes to Python Flask bridge,
 * independently enforces allowlist before sending, and handles humanized delays.
 */

const fs = require('fs');
const path = require('path');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const pino = require('pino');
const axios = require('axios');

const AUTH_FOLDER = path.resolve(__dirname, '../auth_info_baileys');
const BRIDGE_URL = 'http://localhost:5001/process';
const SETTINGS_PATH = path.resolve(__dirname, '../config/settings.json');
const RELATIONSHIP_MAP_PATH = path.resolve(__dirname, '../config/relationship_map.json');
const KILL_SWITCH_PATH = path.resolve(__dirname, '../kill_switch.flag');

const DEFAULT_SETTINGS = {
  dry_run: true,
  min_delay_seconds: 3,
  max_delay_seconds: 12,
};

/**
 * Reads config/settings.json fresh before processing each message.
 * Falls back safely to defaults if file is missing or fails to parse. Never throws.
 */
function loadSettings() {
  try {
    if (fs.existsSync(SETTINGS_PATH)) {
      const raw = fs.readFileSync(SETTINGS_PATH, 'utf-8');
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        return {
          dry_run: typeof parsed.dry_run === 'boolean' ? parsed.dry_run : DEFAULT_SETTINGS.dry_run,
          min_delay_seconds:
            typeof parsed.min_delay_seconds === 'number'
              ? parsed.min_delay_seconds
              : DEFAULT_SETTINGS.min_delay_seconds,
          max_delay_seconds:
            typeof parsed.max_delay_seconds === 'number'
              ? parsed.max_delay_seconds
              : DEFAULT_SETTINGS.max_delay_seconds,
        };
      }
    }
  } catch (err) {
    // Fail-safe to default settings on any error
  }
  return { ...DEFAULT_SETTINGS };
}

/**
 * Checks whether kill_switch.flag exists in the repo root.
 */
function isKillSwitchActive() {
  try {
    return fs.existsSync(KILL_SWITCH_PATH);
  } catch (err) {
    return false;
  }
}

/**
 * Independently enforces allowlist from config/relationship_map.json.
 * Strips JID suffix and returns true only if mapped relationship is present and not 'unknown'.
 */
function enforceAllowlist(jid) {
  if (!jid || typeof jid !== 'string') {
    return false;
  }
  const cleanJid = jid.trim();
  if (!cleanJid) {
    return false;
  }

  // Strip anything after '@'
  const number = cleanJid.includes('@') ? cleanJid.split('@')[0].trim() : cleanJid;
  if (!number) {
    return false;
  }

  try {
    if (fs.existsSync(RELATIONSHIP_MAP_PATH)) {
      const raw = fs.readFileSync(RELATIONSHIP_MAP_PATH, 'utf-8');
      const map = JSON.parse(raw);
      if (map && typeof map === 'object') {
        const mappedRel = map[number];
        if (mappedRel && typeof mappedRel === 'string') {
          return mappedRel.trim().toLowerCase() !== 'unknown';
        }
      }
    }
  } catch (err) {
    return false;
  }
  return false;
}

/**
 * Extracts normalized message fields from a Baileys message object.
 * Handles conversation, extendedTextMessage, image, video, audio captions,
 * and detects forwarded messages without throwing.
 */
function extractMessageDetails(msg) {
  if (!msg || !msg.message) {
    return null;
  }

  // Unwrap potential ephemeral or view-once wrapper layers
  const messageContent =
    msg.message.ephemeralMessage?.message ||
    msg.message.viewOnceMessage?.message ||
    msg.message.viewOnceMessageV2?.message ||
    msg.message;

  if (!messageContent) {
    return null;
  }

  let text = '';
  let message_type = 'other';
  let contextInfo = null;

  if (messageContent.conversation) {
    text = messageContent.conversation;
    message_type = 'text';
  } else if (messageContent.extendedTextMessage) {
    text = messageContent.extendedTextMessage.text || '';
    message_type = 'text';
    contextInfo = messageContent.extendedTextMessage.contextInfo;
  } else if (messageContent.imageMessage) {
    text = messageContent.imageMessage.caption || '';
    message_type = 'image';
    contextInfo = messageContent.imageMessage.contextInfo;
  } else if (messageContent.videoMessage) {
    text = messageContent.videoMessage.caption || '';
    message_type = 'video';
    contextInfo = messageContent.videoMessage.contextInfo;
  } else if (messageContent.audioMessage) {
    text = messageContent.audioMessage.caption || '';
    message_type = 'audio';
    contextInfo = messageContent.audioMessage.contextInfo;
  } else {
    message_type = 'other';
    // Check if any sub-message object has contextInfo
    for (const key of Object.keys(messageContent)) {
      if (messageContent[key] && typeof messageContent[key] === 'object' && messageContent[key].contextInfo) {
        contextInfo = messageContent[key].contextInfo;
        break;
      }
    }
  }

  const is_forwarded = Boolean(
    contextInfo?.isForwarded ||
    messageContent?.extendedTextMessage?.contextInfo?.isForwarded
  );

  return {
    jid: msg.key?.remoteJid || '',
    text: text || '',
    message_type,
    is_forwarded,
    from_me: Boolean(msg.key?.fromMe),
  };
}

/**
 * Main connection loop for Baileys WhatsApp client.
 */
async function connectToWhatsApp() {
  console.log('[CONNECT] Initializing Baileys client...');
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_FOLDER);

  const sock = makeWASocket({
    auth: state,
    logger: pino({ level: 'silent' }),
    printQRInTerminal: false,
    syncFullHistory: false,
  });

  // Handle connection updates & QR display
  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('\n[CONNECT] Scan the QR code below with WhatsApp to pair:\n');
      qrcode.generate(qr, { small: true });
    }

    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      console.log(`[CONNECT] Connection closed (statusCode=${statusCode}). Reconnecting: ${shouldReconnect}`);
      if (shouldReconnect) {
        connectToWhatsApp();
      } else {
        console.log('[CONNECT] Logged out from WhatsApp. Please delete auth_info_baileys and re-scan QR code.');
      }
    } else if (connection === 'open') {
      console.log('[CONNECT] Successfully connected to WhatsApp! Listening for incoming messages...');
    }
  });

  // Save updated credentials to auth_info_baileys
  sock.ev.on('creds.update', saveCreds);

  // Listen for incoming messages
  sock.ev.on('messages.upsert', async (upsert) => {
    // Only process messages where the upsert event's 'type' is exactly 'notify'
    if (upsert.type !== 'notify') {
      console.log('[SKIP] history sync message, ignoring');
      return;
    }

    const messages = upsert.messages || [];
    for (const msg of messages) {
      // 2. Kill switch check before processing
      if (isKillSwitchActive()) {
        console.log('[KILL SWITCH] active, skipping all processing');
        continue;
      }

      // 1. Read fresh settings for this message
      const currentSettings = loadSettings();

      // Skip own messages
      if (msg.key?.fromMe) {
        console.log('[SKIP] own message');
        continue;
      }

      const extracted = extractMessageDetails(msg);
      if (!extracted || !extracted.jid) {
        console.log('[SKIP] empty or unsupported message structure');
        continue;
      }

      console.log(`[ROUTE] Incoming message from ${extracted.jid} (type=${extracted.message_type}, forwarded=${extracted.is_forwarded})`);
      if (extracted.text) {
        console.log(`[ROUTE] Message preview: "${extracted.text.replace(/\n/g, ' ')}"`);
      }

      try {
        // POST to Python Flask bridge
        const response = await axios.post(BRIDGE_URL, {
          jid: extracted.jid,
          text: extracted.text,
          message_type: extracted.message_type,
          is_forwarded: extracted.is_forwarded,
          from_me: extracted.from_me,
        }, {
          headers: { 'Content-Type': 'application/json' },
          timeout: 45000,
        });

        const { should_reply, reply, relationship, reason } = response.data;
        console.log(`[DECISION] Relationship: ${relationship} | Should reply: ${should_reply} | Reason: ${reason}`);

        // Handle reply decision
        if (should_reply && reply && typeof reply === 'string' && reply.trim()) {
          console.log(`[REPLY] Candidate reply generated: "${reply.trim()}"`);

          // 5. If dry_run is true, log and do not send
          if (currentSettings.dry_run) {
            console.log(`[DRY_RUN] would reply to ${extracted.jid}: ${reply.trim()}`);
          } else {
            // 3. Independent allowlist check immediately before sock.sendMessage
            if (!enforceAllowlist(extracted.jid)) {
              console.log(`[BLOCKED] failed independent allowlist check for ${extracted.jid}`);
              continue;
            }

            // 4. Random pre-send delay from dynamic settings
            const minDelay = Math.max(0, currentSettings.min_delay_seconds ?? 3);
            const maxDelay = Math.max(minDelay, currentSettings.max_delay_seconds ?? 12);
            const minMs = minDelay * 1000;
            const maxMs = maxDelay * 1000;
            const delay = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;

            console.log(`[SEND] Waiting ${delay}ms before sending reply to ${extracted.jid}...`);
            await new Promise((resolve) => setTimeout(resolve, delay));

            await sock.sendMessage(extracted.jid, { text: reply.trim() });
            console.log(`[SEND] Reply successfully sent to ${extracted.jid}!`);
          }
        }
      } catch (err) {
        console.error(`[ERROR] Bridge communication failed for ${extracted.jid}: ${err.message}`);
      }
    }
  });
}

// Export functions for unit testing & run client if executed directly
module.exports = {
  loadSettings,
  isKillSwitchActive,
  enforceAllowlist,
  extractMessageDetails,
  connectToWhatsApp,
};

if (require.main === module) {
  connectToWhatsApp().catch((err) => {
    console.error('[FATAL] Failed to start Baileys client:', err);
    process.exit(1);
  });
}
