<template>
  <div class="settings">
    <section class="surface-card settings-card">
      <div class="card-header">
        <div>
          <h2>应用设置</h2>
          <p>配置 API 令牌、令牌验证以及默认合成首选项。</p>
        </div>
      </div>

      <div class="form-container">
        <el-form label-position="top" style="max-width: 500px">
          <el-form-item label="管理令牌 (Admin Token)">
            <el-input v-model="form.adminToken" type="password" show-password placeholder="输入管理令牌以启用写操作" />
            <div class="form-hint">保存设置、删除记录等敏感操作需要此令牌。</div>
          </el-form-item>

          <el-divider />

          <el-form-item label="小米 MiMo API Key">
            <el-input v-model="form.apiKey" type="password" show-password :placeholder="settings.apiKeySet ? '已设置，留空则不修改' : '输入小米 MiMo API Key'" />
            <div class="form-hint">用于语音合成服务。</div>
          </el-form-item>

          <el-form-item label="默认合成音色">
            <el-select v-model="form.defaultVoice" style="width: 100%">
              <el-option v-for="v in presets" :key="v.name" :label="v.name" :value="v.name" />
            </el-select>
          </el-form-item>

          <el-divider />

          <el-form-item label="DeepSeek API Key">
            <el-input v-model="form.deepseekApiKey" type="password" show-password :placeholder="settings.deepseekApiKeySet ? '已设置，留空则不修改' : '输入 DeepSeek API Key'" />
            <div class="form-hint">用于 AI 创作和字幕翻译功能。</div>
          </el-form-item>
          <el-form-item label="DeepSeek API 地址">
            <el-input v-model="form.deepseekBaseUrl" placeholder="https://api.deepseek.com/v1" />
          </el-form-item>
          <el-form-item label="默认翻译/润色模型">
            <el-input v-model="form.deepseekModel" placeholder="deepseek-chat" />
          </el-form-item>

          <el-divider />

          <h3 class="section-title">字幕翻译设置</h3>

          <el-form-item label="默认 ASR 引擎">
            <el-select v-model="form.subtitleAsrEngine" style="width: 100%">
              <el-option label="Faster-Whisper (本地)" value="whisper" />
              <el-option label="OpenAI Whisper API" value="whisper_api" />
              <el-option label="讯飞语音" value="xunfei" />
            </el-select>
          </el-form-item>

          <el-form-item v-if="form.subtitleAsrEngine === 'whisper'" label="Whisper 模型">
            <el-select v-model="form.subtitleFasterWhisperModel" style="width: 100%">
              <el-option v-for="m in whisperModels" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>

          <el-alert
            v-if="form.subtitleAsrEngine === 'whisper' && gpuStatus && !gpuStatus.ok"
            type="error"
            :title="'本地 Whisper GPU 运行时不可用'"
            :description="gpuStatus.message"
            show-icon
            :closable="false"
            style="margin-bottom: 16px"
          />
          <el-tag
            v-if="form.subtitleAsrEngine === 'whisper' && gpuStatus && gpuStatus.ok"
            type="success"
            size="small"
            style="margin-bottom: 16px"
          >GPU 运行时正常</el-tag>

          <el-form-item label="OpenAI Whisper API Key" v-if="form.subtitleAsrEngine === 'whisper_api'">
            <el-input v-model="form.whisperApiKey" type="password" show-password :placeholder="settings.whisperApiKeySet ? '已设置，留空则不修改' : '输入 OpenAI API Key'" />
          </el-form-item>
          <template v-if="form.subtitleAsrEngine === 'whisper_api'">
            <el-form-item label="OpenAI Whisper API 地址">
              <el-input v-model="form.whisperApiBaseUrl" placeholder="https://api.openai.com/v1" />
            </el-form-item>
            <el-form-item label="Whisper API 模型">
              <el-input v-model="form.subtitleWhisperApiModel" placeholder="whisper-1" />
            </el-form-item>
          </template>

          <template v-if="form.subtitleAsrEngine === 'xunfei'">
            <el-form-item label="讯飞 APPID">
              <el-input v-model="form.xunfeiAppid" :placeholder="settings.xunfeiAppid || '输入讯飞 APPID'" />
            </el-form-item>
            <el-form-item label="讯飞 API Key">
              <el-input v-model="form.xunfeiApiKey" type="password" show-password :placeholder="settings.xunfeiApiKeySet ? '已设置，留空则不修改' : '输入讯飞 API Key'" />
            </el-form-item>
            <el-form-item label="讯飞 API Secret">
              <el-input v-model="form.xunfeiApiSecret" type="password" show-password :placeholder="settings.xunfeiApiSecretSet ? '已设置，留空则不修改' : '输入讯飞 API Secret'" />
            </el-form-item>
          </template>

          <el-form-item label="默认识别源语言">
            <el-select v-model="form.subtitleSourceLanguage" style="width: 100%">
              <el-option label="自动检测" value="auto" />
              <el-option v-for="lang in sourceLanguages" :key="lang.value" :label="lang.label" :value="lang.value" />
            </el-select>
          </el-form-item>

          <el-form-item label="默认目标语言">
            <el-select v-model="form.subtitleTargetLanguage" filterable allow-create style="width: 100%">
              <el-option v-for="lang in languages" :key="lang" :label="lang" :value="lang" />
            </el-select>
          </el-form-item>

          <div class="form-actions">
            <el-button type="primary" size="large" @click="handleSave" :loading="saving">保存所有设置</el-button>
          </div>
        </el-form>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getPresets } from '../api/voices'
import { getLocalWhisperRuntimeStatus } from '../api/subtitle'
import { useSettingsStore } from '../stores/settings'

const settings = useSettingsStore()
const presets = ref([])
const saving = ref(false)
const gpuStatus = ref(null)

async function checkGpuStatus() {
  try {
    const { data } = await getLocalWhisperRuntimeStatus()
    gpuStatus.value = data
  } catch {
    gpuStatus.value = { ok: false, missing: ['unknown'], message: '无法获取 GPU 运行时状态' }
  }
}

const whisperModels = ['tiny', 'base', 'small', 'medium', 'large']
const languages = ['简体中文', '繁體中文', 'English', '日本語', '한국어', 'Français', 'Deutsch', 'Español']
const sourceLanguages = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
  { value: 'ja', label: '日本語' },
  { value: 'ko', label: '한국어' },
  { value: 'fr', label: 'Français' },
  { value: 'de', label: 'Deutsch' },
  { value: 'es', label: 'Español' },
]

const form = ref({
  apiKey: '',
  defaultVoice: '冰糖',
  adminToken: '',
  deepseekApiKey: '',
  deepseekBaseUrl: 'https://api.deepseek.com/v1',
  deepseekModel: 'deepseek-chat',
  whisperApiKey: '',
  whisperApiBaseUrl: 'https://api.openai.com/v1',
  xunfeiAppid: '',
  xunfeiApiKey: '',
  xunfeiApiSecret: '',
  subtitleAsrEngine: 'whisper',
  subtitleFasterWhisperModel: 'base',
  subtitleWhisperApiModel: 'whisper-1',
  subtitleSourceLanguage: 'auto',
  subtitleTargetLanguage: '简体中文',
})

watch(() => form.value.subtitleAsrEngine, (engine) => {
  if (engine === 'whisper') checkGpuStatus()
})

onMounted(async () => {
  try {
    const { data } = await getPresets()
    presets.value = data
  } catch {
    ElMessage.error('加载音色列表失败')
  }
  await settings.loadSettings()
  form.value.defaultVoice = settings.defaultVoice
  form.value.adminToken = settings.adminToken
  form.value.deepseekBaseUrl = settings.deepseekBaseUrl
  form.value.deepseekModel = settings.deepseekModel
  form.value.whisperApiBaseUrl = settings.whisperApiBaseUrl
  form.value.subtitleAsrEngine = settings.subtitleAsrEngine
  form.value.subtitleFasterWhisperModel = settings.subtitleFasterWhisperModel
  form.value.subtitleWhisperApiModel = settings.subtitleWhisperApiModel
  form.value.subtitleSourceLanguage = settings.subtitleSourceLanguage
  form.value.subtitleTargetLanguage = settings.subtitleTargetLanguage
  form.value.xunfeiAppid = settings.xunfeiAppid
  if (form.value.subtitleAsrEngine === 'whisper') checkGpuStatus()
})

async function handleSave() {
  saving.value = true
  try {
    settings.setAdminToken(form.value.adminToken)
    settings.apiKey = form.value.apiKey
    settings.defaultVoice = form.value.defaultVoice
    settings.deepseekApiKey = form.value.deepseekApiKey
    settings.deepseekBaseUrl = form.value.deepseekBaseUrl
    settings.deepseekModel = form.value.deepseekModel
    settings.whisperApiKey = form.value.whisperApiKey
    settings.whisperApiBaseUrl = form.value.whisperApiBaseUrl
    settings.xunfeiAppid = form.value.xunfeiAppid
    settings.xunfeiApiKey = form.value.xunfeiApiKey
    settings.xunfeiApiSecret = form.value.xunfeiApiSecret
    settings.subtitleAsrEngine = form.value.subtitleAsrEngine
    settings.subtitleFasterWhisperModel = form.value.subtitleFasterWhisperModel
    settings.subtitleWhisperApiModel = form.value.subtitleWhisperApiModel
    settings.subtitleSourceLanguage = form.value.subtitleSourceLanguage
    settings.subtitleTargetLanguage = form.value.subtitleTargetLanguage
    await settings.saveSettings()
    ElMessage.success('设置已保存')
    form.value.apiKey = ''
    form.value.deepseekApiKey = ''
    form.value.whisperApiKey = ''
    form.value.xunfeiApiKey = ''
    form.value.xunfeiApiSecret = ''
    await settings.loadSettings()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.settings-card {
  padding: 24px;
  max-width: 800px;
}

.card-header {
  margin-bottom: 32px;
}

.card-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.card-header p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 13px;
}

.form-container {
  padding: 8px 0;
}

.form-hint {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 8px;
  line-height: 1.5;
}

.form-actions {
  margin-top: 32px;
}

:deep(.el-divider--horizontal) {
  margin: 24px 0;
  border-top-color: #f1f5f9;
}

.section-title {
  margin: 0 0 16px;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}
</style>
