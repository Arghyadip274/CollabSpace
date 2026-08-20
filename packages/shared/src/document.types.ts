// Document types shared between frontend (editor) and API

export interface Document {
  id: string
  workspaceId: string
  creatorId: string
  title: string
  content: string
  revision: number
  createdAt: string
  updatedAt: string
}

export interface DocumentVersion {
  id: string
  documentId: string
  revision: number
  snapshot: string
  createdAt: string
}
