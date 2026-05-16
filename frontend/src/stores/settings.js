import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

export const useSettingsStore = defineStore('settings', () => {
  const apiKey = ref('')
  const apiKeySet = ref(false)
  const defaultVoice = ref('冰糖')
  const adminToken = ref(localStorage.getItem('admin_token') || '')
  const deepseekApiKey = ref('')
  const deepseekApiKeySet = ref(false)

  // Subtitle settings
  const whisperApiKey = ref('')
  const whisperApiKeySet = ref(false)
  const whisperApiBaseUrl = ref('https://api.openai.com/v1')
  const xunfeiAppid = ref('')
  const xunfeiApiKey = ref('')
  const xunfeiApiKeySet = ref(false)
  const xunfeiApiSecret = ref('')
  const xunfeiApiSecretSet = ref(false)
  const subtitleAsrEngine = ref('whisper')
  const subtitleFasterWhisperModel = ref('base')
  const subtitleWhisperApiModel = ref('whisper-1')
  const subtitleTargetLanguage = ref('简体中文')

  function setAdminToken(token) {
    adminToken.value = token
    if (token) {
      localStorage.setItem('admin_token', token)
    } else {
      localStorage.removeItem('admin_token')
    }
  }

  async function loadSettings() {
    try {
      const { data } = await api.get('/settings')
      apiKeySet.value = data.mimo_api_key_set || false
      deepseekApiKeySet.value = data.deepseek_api_key_set || false
      if (data.default_voice) defaultVoice.value = data.default_voice

      // Subtitle settings
      whisperApiKeySet.value = data.whisper_api_key_set || false
      if (data.whisper_api_base_url) whisperApiBaseUrl.value = data.whisper_api_base_url
      xunfeiAppid.value = data.xunfei_appid || ''
      xunfeiApiKeySet.value = data.xunfei_api_key_set || false
      xunfeiApiSecretSet.value = data.xunfei_api_secret_set || false
      if (data.subtitle_asr_engine) subtitleAsrEngine.value = data.subtitle_asr_engine
      if (data.subtitle_faster_whisper_model) subtitleFasterWhisperModel.value = data.subtitle_faster_whisper_model
      if (data.subtitle_whisper_api_model) subtitleWhisperApiModel.value = data.subtitle_whisper_api_model
      if (data.subtitle_target_language) subtitleTargetLanguage.value = data.subtitle_target_language
    } catch {
      ElMessage.error('加载设置失败')
    }
  }

  async function saveSettings() {
    const payload = { default_voice: defaultVoice.value }
    if (apiKey.value) payload.mimo_api_key = apiKey.value
    if (deepseekApiKey.value) payload.deepseek_api_key = deepseekApiKey.value
    if (whisperApiKey.value) payload.whisper_api_key = whisperApiKey.value
    if (whisperApiBaseUrl.value) payload.whisper_api_base_url = whisperApiBaseUrl.value
    if (xunfeiAppid.value) payload.xunfei_appid = xunfeiAppid.value
    if (xunfeiApiKey.value) payload.xunfei_api_key = xunfeiApiKey.value
    if (xunfeiApiSecret.value) payload.xunfei_api_secret = xunfeiApiSecret.value
    payload.subtitle_asr_engine = subtitleAsrEngine.value
    payload.subtitle_faster_whisper_model = subtitleFasterWhisperModel.value
    payload.subtitle_whisper_api_model = subtitleWhisperApiModel.value
    payload.subtitle_target_language = subtitleTargetLanguage.value
    await api.put('/settings', payload, {
      headers: { 'X-Admin-Token': adminToken.value }
    })
  }

  return {
    apiKey, apiKeySet, defaultVoice, adminToken,
    deepseekApiKey, deepseekApiKeySet,
    whisperApiKey, whisperApiKeySet, whisperApiBaseUrl,
    xunfeiAppid, xunfeiApiKey, xunfeiApiKeySet, xunfeiApiSecret, xunfeiApiSecretSet,
    subtitleAsrEngine, subtitleFasterWhisperModel, subtitleWhisperApiModel, subtitleTargetLanguage,
    setAdminToken, loadSettings, saveSettings,
  }
})
