<template>
  <div class="settings">
    <h2>设置</h2>
    <el-card style="max-width: 600px">
      <el-form label-width="100px">
        <el-form-item label="管理令牌">
          <el-input v-model="form.adminToken" type="password" show-password placeholder="输入管理令牌以启用写操作" />
          <div style="font-size: 12px; color: #909399; margin-top: 4px">保存设置、删除记录等操作需要此令牌。令牌在后端环境变量 ADMIN_TOKEN 中配置。</div>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.apiKey" type="password" show-password :placeholder="settings.apiKeySet ? '已设置，留空则不修改' : '输入小米 MiMo API Key'" />
        </el-form-item>
        <el-form-item label="默认音色">
          <el-select v-model="form.defaultVoice" style="width: 200px">
            <el-option v-for="v in presets" :key="v.name" :label="v.name" :value="v.name" />
          </el-select>
        </el-form-item>
        <el-divider />
        <el-form-item label="DeepSeek Key">
          <el-input v-model="form.deepseekApiKey" type="password" show-password :placeholder="settings.deepseekApiKeySet ? '已设置，留空则不修改' : '输入 DeepSeek API Key'" />
          <div style="font-size: 12px; color: #909399; margin-top: 4px">用于 AI 创作功能，调用 DeepSeek 生成听书内容。</div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getPresets } from '../api/voices'
import { useSettingsStore } from '../stores/settings'

const settings = useSettingsStore()
const presets = ref([])
const saving = ref(false)
const form = ref({
  apiKey: '',
  defaultVoice: '冰糖',
  adminToken: '',
  deepseekApiKey: '',
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
})

async function handleSave() {
  saving.value = true
  try {
    settings.setAdminToken(form.value.adminToken)
    settings.apiKey = form.value.apiKey
    settings.defaultVoice = form.value.defaultVoice
    settings.deepseekApiKey = form.value.deepseekApiKey
    await settings.saveSettings()
    ElMessage.success('设置已保存')
    form.value.apiKey = ''
    form.value.deepseekApiKey = ''
    await settings.loadSettings()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>
