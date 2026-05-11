<template>
  <div class="voice-manage">
    <h2>音色管理</h2>

    <el-tabs>
      <el-tab-pane label="预置音色">
        <el-table :data="presets">
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="language" label="语言" />
          <el-table-column prop="gender" label="性别" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="音色设计">
        <el-form label-width="100px" style="max-width: 600px">
          <el-form-item label="音色名称">
            <el-input v-model="designForm.name" />
          </el-form-item>
          <el-form-item label="音色描述">
            <el-input v-model="designForm.description" type="textarea" :rows="3" placeholder="例如：年轻女性，温柔甜美，语速适中" />
          </el-form-item>
          <el-form-item label="试听文本">
            <el-input v-model="designForm.sample_text" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleDesign" :loading="designing">创建音色</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="音色克隆">
        <el-form label-width="100px" style="max-width: 600px">
          <el-form-item label="音色名称">
            <el-input v-model="cloneForm.name" />
          </el-form-item>
          <el-form-item label="音频样本">
            <el-upload :auto-upload="false" :limit="1" accept=".mp3,.wav" @change="handleFileChange">
              <el-button>选择文件</el-button>
              <template #tip>
                <div class="el-upload__tip">支持 mp3/wav 格式，最大 10MB</div>
              </template>
            </el-upload>
          </el-form-item>
          <el-form-item label="试听文本">
            <el-input v-model="cloneForm.sample_text" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleClone" :loading="cloning">创建音色</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="我的音色">
        <el-table :data="customVoices">
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="type" label="类型">
            <template #default="{ row }">{{ row.type === 'design' ? '设计' : '克隆' }}</template>
          </el-table-column>
          <el-table-column prop="description" label="描述" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button size="small" @click="playPreview(row)">试听</el-button>
              <el-button size="small" type="danger" @click="handleDeleteVoice(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getPresets, getCustomVoices, designVoice, cloneVoice, deleteVoice, getVoicePreviewUrl } from '../api/voices'
import { usePlayerStore } from '../stores/player'

const player = usePlayerStore()
const presets = ref([])
const customVoices = ref([])
const designing = ref(false)
const cloning = ref(false)
const cloneFile = ref(null)

const designForm = ref({ name: '', description: '', sample_text: '你好，欢迎来到我的听书世界。' })
const cloneForm = ref({ name: '', sample_text: '你好，欢迎来到我的听书世界。' })

onMounted(async () => {
  const { data } = await getPresets()
  presets.value = data
  loadCustom()
})

async function loadCustom() {
  const { data } = await getCustomVoices()
  customVoices.value = data
}

async function handleDesign() {
  if (!designForm.value.name || !designForm.value.description) {
    ElMessage.warning('请填写名称和描述')
    return
  }
  designing.value = true
  try {
    await designVoice(designForm.value)
    ElMessage.success('音色创建成功')
    designForm.value = { name: '', description: '', sample_text: '你好，欢迎来到我的听书世界。' }
    loadCustom()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    designing.value = false
  }
}

function handleFileChange(file) {
  cloneFile.value = file.raw
}

async function handleClone() {
  if (!cloneForm.value.name || !cloneFile.value) {
    ElMessage.warning('请填写名称并上传音频样本')
    return
  }
  cloning.value = true
  try {
    const fd = new FormData()
    fd.append('file', cloneFile.value)
    fd.append('name', cloneForm.value.name)
    fd.append('sample_text', cloneForm.value.sample_text)
    await cloneVoice(fd)
    ElMessage.success('音色创建成功')
    cloneForm.value = { name: '', sample_text: '你好，欢迎来到我的听书世界。' }
    cloneFile.value = null
    loadCustom()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    cloning.value = false
  }
}

function playPreview(row) {
  player.playUrl(getVoicePreviewUrl(row.id), {
    title: `${row.name} 试听`,
    sourceType: 'preview',
  })
}

async function handleDeleteVoice(row) {
  try {
    await deleteVoice(row.id)
    ElMessage.success('已删除')
    loadCustom()
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>
