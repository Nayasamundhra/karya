/**
 * Global toast queue — the second (and last) piece of genuinely global
 * client state in this app. Notifications can be triggered from anywhere
 * (a mutation's `onError`, a route-level effect) with no component tree
 * position in common, which is exactly the case Zustand is for.
 *
 * Server data (attendance, users, ...) must never be duplicated in here —
 * TanStack Query already owns that. See §22/§23.
 */
import { create } from 'zustand'

export type ToastVariant = 'default' | 'success' | 'danger'

export interface ToastItem {
  id: string
  title: string
  description?: string
  variant: ToastVariant
}

interface ToastState {
  toasts: ToastItem[]
  push: (toast: Omit<ToastItem, 'id'>) => void
  dismiss: (id: string) => void
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (toast) => set((state) => ({ toasts: [...state.toasts, { id: crypto.randomUUID(), ...toast }] })),
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}))

/**
 * The imperative API components actually call — `toast.success('Saved')`
 * rather than wiring up the store's `push` at every call site. Toasts are
 * for things like "profile updated" and "password changed" (§28); an
 * attendance result is displayed prominently in the flow itself (Phase 9),
 * never only as a toast that can be missed.
 */
export const toast = {
  success: (title: string, description?: string) => useToastStore.getState().push({ title, description, variant: 'success' }),
  error: (title: string, description?: string) => useToastStore.getState().push({ title, description, variant: 'danger' }),
  info: (title: string, description?: string) => useToastStore.getState().push({ title, description, variant: 'default' }),
}
