import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './en.json'
import fr from './fr.json'

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    fr: { translation: fr },
  },
  lng: localStorage.getItem('language') || 'en',
  fallbackLng: 'en',
  interpolation: {
    // Enable HTML escaping to prevent XSS attacks
    // React already escapes by default, but this provides defense-in-depth
    escapeValue: true,
  },
})

export default i18n
