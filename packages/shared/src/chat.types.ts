// Chat / messaging types

export interface Channel {
  id: string
  workspaceId: string
  name: string
  type: 'PUBLIC' | 'PRIVATE' | 'DIRECT'
  createdAt: string
}

export interface Message {
  id: string
  channelId: string
  authorId: string
  content: string
  editedAt?: string
  createdAt: string
}

export interface Presence {
  userId: string
  status: 'online' | 'offline' | 'typing'
  lastSeen: string
}
