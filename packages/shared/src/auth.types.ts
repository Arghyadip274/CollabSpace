// Auth & user types shared between frontend and API contracts

export interface User {
  id: string
  email: string
  name: string
  avatarUrl?: string
  createdAt: string
}

export interface AuthTokens {
  accessToken: string
  refreshToken: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  name: string
  password: string
}

export interface WorkspaceRole {
  role: 'OWNER' | 'ADMIN' | 'MEMBER'
}
