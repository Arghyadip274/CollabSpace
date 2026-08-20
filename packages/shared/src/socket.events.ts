// Socket.io event name constants + payload types
// Keep in sync with apps/backend/src/realtime/events.py

// --- Document namespace (/doc) ------------------------------------------------
export const DOC_EVENTS = {
  JOIN_ROOM:  'doc:join',
  LEAVE_ROOM: 'doc:leave',
  OP_SEND:    'doc:op:send',    // client ? server
  OP_BROADCAST: 'doc:op:broadcast', // server ? clients
  CURSOR:     'doc:cursor',
} as const

// --- Chat namespace (/chat) ---------------------------------------------------
export const CHAT_EVENTS = {
  JOIN_CHANNEL:  'chat:join',
  LEAVE_CHANNEL: 'chat:leave',
  MESSAGE_SEND:  'chat:message:send',
  MESSAGE_NEW:   'chat:message:new',
  MESSAGE_EDIT:  'chat:message:edit',
  MESSAGE_DELETE:'chat:message:delete',
  TYPING_START:  'chat:typing:start',
  TYPING_STOP:   'chat:typing:stop',
  PRESENCE:      'chat:presence',
} as const

// --- Notification events ------------------------------------------------------
export const NOTIFICATION_EVENTS = {
  NEW: 'notification:new',
} as const
