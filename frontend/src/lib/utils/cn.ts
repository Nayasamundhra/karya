import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge conditional class names, with Tailwind-aware conflict resolution
 * (a later `px-4` wins over an earlier `px-2` instead of both surviving). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
