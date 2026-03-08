import { toast } from 'sonner'
import i18n from '@/i18n'

type ToastParams = Record<string, string | number>

export const showToast = {
  success(messageOrKey: string, params?: ToastParams) {
    const message = i18n.exists(messageOrKey) ? i18n.t(messageOrKey, params) : messageOrKey
    toast.success(message)
  },
  error(messageOrKey: string, params?: ToastParams) {
    const message = i18n.exists(messageOrKey) ? i18n.t(messageOrKey, params) : messageOrKey
    toast.error(message)
  },
  info(messageOrKey: string, params?: ToastParams) {
    const message = i18n.exists(messageOrKey) ? i18n.t(messageOrKey, params) : messageOrKey
    toast.info(message)
  },
  warning(messageOrKey: string, params?: ToastParams) {
    const message = i18n.exists(messageOrKey) ? i18n.t(messageOrKey, params) : messageOrKey
    toast.warning(message)
  },
}
