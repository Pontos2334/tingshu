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
    } catch {
      ElMessage.error('加载设置失败')
    }
  }

  async function saveSettings() {
    const payload = { default_voice: defaultVoice.value }
    if (apiKey.value) {
      payload.mimo_api_key = apiKey.value
    }
    if (deepseekApiKey.value) {
      payload.deepseek_api_key = deepseekApiKey.value
    }
    await api.put('/settings', payload, {
      headers: { 'X-Admin-Token': adminToken.value }
    })
  }

  return {
    apiKey, apiKeySet, defaultVoice, adminToken,
    deepseekApiKey, deepseekApiKeySet,
    setAdminToken, loadSettings, saveSettings,
  }
})
