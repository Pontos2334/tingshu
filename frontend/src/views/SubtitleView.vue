<template>
  <div class="subtitle-view">
    <!-- Left: Project List -->
    <div class="project-list surface-card">
      <div class="list-header">
        <h3>字幕项目</h3>
        <el-button type="primary" size="small" @click="showCreateDialog = true">新建项目</el-button>
      </div>
      <el-input v-model="store.searchQuery" placeholder="搜索项目..." clearable size="small" style="margin-bottom: 12px" @input="debouncedLoad" />
      <div class="list-body">
        <div
          v-for="p in projects" :key="p.id"
          class="project-item"
          :class="{ active: store.currentProjectId === p.id }"
          @click="selectProject(p)"
        >
          <div class="project-name">{{ p.name }}</div>
          <div class="project-meta">
            <el-tag :type="statusType(p.status)" size="small">{{ statusLabel(p.status) }}</el-tag>
            <span class="meta-text">{{ p.segment_count }} 段</span>
          </div>
        </div>
        <el-empty v-if="!projects.length" description="暂无项目" :image-size="60" />
      </div>
      <div class="list-footer">
        <el-pagination
          size="small" layout="prev, pager, next"
          :total="total" :page-size="pageSize"
          v-model:current-page="store.currentPage"
          @current-change="loadProjects"
        />
      </div>
    </div>

    <!-- Right: Project Detail -->
    <div class="project-detail">
      <template v-if="store.project">
        <div class="detail-header surface-card">
          <div class="header-row">
            <h2>{{ store.project.name }}</h2>
            <el-tag :type="statusType(store.project.status)" size="small">{{ statusLabel(store.project.status) }}</el-tag>
            <div class="header-actions">
              <el-button size="small" @click="showEditDialog = true">项目设置</el-button>
              <el-button size="small" @click="refreshProject">刷新</el-button>
              <el-button size="small" type="danger" @click="handleDelete">删除</el-button>
            </div>
          </div>
        </div>

        <!-- Upload Section -->
        <div class="surface-card section-card">
          <h4>视频源</h4>
          <SubtitleUpload :project="store.project" @updated="refreshProject" />
        </div>

        <!-- Pipeline Section -->
        <div class="surface-card section-card">
          <h4>处理管线</h4>
          <el-alert
            v-if="store.project.asr_engine === 'whisper' && gpuStatus && !gpuStatus.ok"
            type="warning"
            title="本地 Whisper GPU 运行时不可用"
            :description="gpuStatus.message"
            show-icon
            :closable="false"
            style="margin-bottom: 12px"
          />
          <SubtitlePipeline
            :project="store.project"
            :has-segments="store.segments.length > 0"
            @process="handleProcess"
            @cancel="handleCancel"
          />
        </div>

        <!-- Subtitle Table -->
        <div v-if="store.segments.length" class="surface-card section-card table-section">
          <div class="table-header">
            <h4>字幕片段 ({{ store.segments.length }})</h4>
            <el-button size="small" @click="refreshProject">刷新</el-button>
          </div>
          <SubtitleTable
            :project-id="store.project.id"
            :segments="store.segments"
            @updated="refreshProject"
          />
        </div>

        <!-- Export Section -->
        <div class="surface-card section-card">
          <h4>导出</h4>
          <div class="export-form">
            <el-select v-model="exportFormat" style="width: 120px">
              <el-option label="SRT" value="srt" />
              <el-option label="VTT" value="vtt" />
              <el-option label="TXT" value="txt" />
            </el-select>
            <el-select v-model="exportVariant" style="width: 120px">
              <el-option label="双语" value="bilingual" />
              <el-option label="原文" value="original" />
              <el-option label="译文" value="translated" />
              <el-option label="润色" value="polished" />
            </el-select>
            <el-button type="primary" @click="handleExport" :loading="exporting">导出</el-button>
          </div>
          <div v-if="outputs.length" class="outputs-list">
            <div v-for="out in outputs" :key="out.id" class="output-item">
              <span>{{ out.format.toUpperCase() }} · {{ variantLabel(out.variant) }}</span>
              <el-button size="small" type="primary" link @click="handleDownload(out)">下载</el-button>
            </div>
          </div>
        </div>
      </template>

      <el-empty v-else description="选择或创建一个字幕项目" />
    </div>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreateDialog" title="新建字幕项目" width="480px">
      <el-form label-position="top">
        <el-form-item label="项目名称">
          <el-input v-model="newProject.name" placeholder="输入项目名称" />
        </el-form-item>
        <el-form-item label="ASR 引擎">
          <el-select v-model="newProject.asr_engine" style="width: 100%">
            <el-option label="Faster-Whisper (本地)" value="whisper" />
            <el-option label="OpenAI Whisper API" value="whisper_api" />
            <el-option label="讯飞语音" value="xunfei" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="newProject.asr_engine === 'whisper'" label="Whisper 模型">
          <el-select v-model="newProject.faster_whisper_model" style="width: 100%">
            <el-option v-for="m in whisperModels" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="newProject.asr_engine === 'whisper_api'" label="Whisper API 模型">
          <el-input v-model="newProject.whisper_api_model" placeholder="whisper-1" />
        </el-form-item>
        <el-form-item label="识别源语言">
          <el-select v-model="newProject.source_language" style="width: 100%">
            <el-option label="自动检测" value="auto" />
            <el-option v-for="lang in sourceLanguages" :key="lang.value" :label="lang.label" :value="lang.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="翻译/润色模型">
          <el-input v-model="newProject.translator_model" placeholder="deepseek-chat" />
        </el-form-item>
        <el-form-item label="目标语言">
          <el-select v-model="newProject.target_language" filterable allow-create style="width: 100%">
            <el-option v-for="lang in languages" :key="lang" :label="lang" :value="lang" />
          </el-select>
        </el-form-item>
        <el-form-item label="上下文提示 (可选)">
          <el-input v-model="newProject.context_hint" type="textarea" :rows="2" placeholder="描述视频内容以提高翻译质量，如：Python 编程教程" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate" :loading="creating">创建</el-button>
      </template>
    </el-dialog>

    <!-- Edit Config Dialog -->
    <el-dialog v-model="showEditDialog" title="编辑项目配置" width="480px">
      <el-form label-position="top" v-if="editProject">
        <el-form-item label="项目名称">
          <el-input v-model="editProject.name" placeholder="输入项目名称" />
        </el-form-item>
        <el-form-item label="ASR 引擎">
          <el-select v-model="editProject.asr_engine" style="width: 100%">
            <el-option label="Faster-Whisper (本地)" value="whisper" />
            <el-option label="OpenAI Whisper API" value="whisper_api" />
            <el-option label="讯飞语音" value="xunfei" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editProject.asr_engine === 'whisper'" label="Whisper 模型">
          <el-select v-model="editProject.faster_whisper_model" style="width: 100%">
            <el-option v-for="m in whisperModels" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editProject.asr_engine === 'whisper_api'" label="Whisper API 模型">
          <el-input v-model="editProject.whisper_api_model" placeholder="whisper-1" />
        </el-form-item>
        <el-form-item label="识别源语言">
          <el-select v-model="editProject.source_language" style="width: 100%">
            <el-option label="自动检测" value="auto" />
            <el-option v-for="lang in sourceLanguages" :key="lang.value" :label="lang.label" :value="lang.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="翻译/润色模型">
          <el-input v-model="editProject.translator_model" placeholder="deepseek-chat" />
        </el-form-item>
        <el-form-item label="目标语言">
          <el-select v-model="editProject.target_language" filterable allow-create style="width: 100%">
            <el-option v-for="lang in languages" :key="lang" :label="lang" :value="lang" />
          </el-select>
        </el-form-item>
        <el-form-item label="上下文提示 (可选)">
          <el-input v-model="editProject.context_hint" type="textarea" :rows="2" placeholder="描述视频内容以提高翻译质量" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSaveEdit" :loading="savingEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSubtitleStore } from '../stores/subtitle'
import { useSettingsStore } from '../stores/settings'
import {
  createSubtitleProject, getSubtitleProjects, getSubtitleProject,
  updateSubtitleProject, deleteSubtitleProject, startSubtitleProcess, cancelSubtitleProcess,
  exportSubtitles, getSubtitleOutputs, downloadSubtitleOutput, getSubtitleEventsUrl,
  getLocalWhisperRuntimeStatus,
} from '../api/subtitle'
import SubtitleUpload from '../components/SubtitleUpload.vue'
import SubtitlePipeline from '../components/SubtitlePipeline.vue'
import SubtitleTable from '../components/SubtitleTable.vue'

const store = useSubtitleStore()
const settingsStore = useSettingsStore()

const projects = ref([])
const total = ref(0)
const pageSize = 20
const outputs = ref([])
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const creating = ref(false)
const savingEdit = ref(false)
const exporting = ref(false)
const editProject = ref(null)
const gpuStatus = ref(null)
const exportFormat = ref('srt')
const exportVariant = ref('bilingual')

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

const newProject = ref({
  name: '',
  asr_engine: 'whisper',
  faster_whisper_model: 'base',
  whisper_api_model: 'whisper-1',
  source_language: 'auto',
  target_language: '简体中文',
  translator_model: 'deepseek-chat',
  context_hint: '',
})

let debounceTimer = null
function debouncedLoad() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => loadProjects(), 300)
}

onMounted(async () => {
  await settingsStore.loadSettings()
  // Initialize newProject defaults from settings
  newProject.value.asr_engine = settingsStore.subtitleAsrEngine
  newProject.value.faster_whisper_model = settingsStore.subtitleFasterWhisperModel
  newProject.value.whisper_api_model = settingsStore.subtitleWhisperApiModel
  newProject.value.source_language = settingsStore.subtitleSourceLanguage
  newProject.value.target_language = settingsStore.subtitleTargetLanguage
  newProject.value.translator_model = settingsStore.deepseekModel
  await loadProjects()
  if (store.currentProjectId) {
    await selectProjectById(store.currentProjectId)
  }
})

async function loadProjects() {
  try {
    const { data } = await getSubtitleProjects({ page: store.currentPage, page_size: pageSize, search: store.searchQuery })
    projects.value = data.items
    total.value = data.total
  } catch {
    ElMessage.error('加载项目列表失败')
  }
}

async function selectProject(p) {
  await selectProjectById(p.id)
}

async function selectProjectById(id) {
  try {
    const { data } = await getSubtitleProject(id)
    store.setProject(data)
    store.currentProjectId = id
    outputs.value = data.outputs || []
    // Sync editProject for the edit dialog
    editProject.value = {
      name: data.name,
      asr_engine: data.asr_engine,
      faster_whisper_model: data.faster_whisper_model || 'base',
      whisper_api_model: data.whisper_api_model || 'whisper-1',
      source_language: data.source_language || 'auto',
      target_language: data.target_language,
      translator_model: data.translator_model || 'deepseek-chat',
      context_hint: data.context_hint || '',
    }
    if (data.current_step) {
      store.connectSSE(getSubtitleEventsUrl(id), refreshProject)
    }
    // Check GPU status for local whisper projects
    if (data.asr_engine === 'whisper') {
      checkGpuStatus()
    } else {
      gpuStatus.value = null
    }
  } catch {
    ElMessage.error('加载项目详情失败')
  }
}

async function checkGpuStatus() {
  try {
    const { data } = await getLocalWhisperRuntimeStatus()
    gpuStatus.value = data
  } catch {
    gpuStatus.value = { ok: false, missing: ['unknown'], message: '无法获取 GPU 运行时状态' }
  }
}

async function refreshProject() {
  if (store.currentProjectId) {
    await selectProjectById(store.currentProjectId)
    await loadProjects()
  }
}

async function handleCreate() {
  if (!newProject.value.name.trim()) {
    ElMessage.warning('请输入项目名称')
    return
  }
  creating.value = true
  try {
    const { data } = await createSubtitleProject(newProject.value)
    showCreateDialog.value = false
    ElMessage.success('项目创建成功')
    newProject.value.name = ''
    await loadProjects()
    await selectProjectById(data.id)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

async function handleSaveEdit() {
  if (!editProject.value || !store.currentProjectId) return
  savingEdit.value = true
  try {
    await updateSubtitleProject(store.currentProjectId, editProject.value)
    ElMessage.success('项目配置已更新')
    showEditDialog.value = false
    await refreshProject()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    savingEdit.value = false
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm('确定删除此项目？所有相关文件将被永久删除。', '确认删除', { type: 'warning' })
    await deleteSubtitleProject(store.currentProjectId)
    ElMessage.success('项目已删除')
    store.clearProject()
    outputs.value = []
    await loadProjects()
  } catch { /* cancelled */ }
}

async function handleProcess(targetStep) {
  if (!store.currentProjectId) return
  const confirmed = await confirmProcessOverwrite(targetStep)
  if (!confirmed) return
  try {
    await startSubtitleProcess(store.currentProjectId, { target_step: targetStep, force: false })
    store.connectSSE(getSubtitleEventsUrl(store.currentProjectId), refreshProject)
    ElMessage.success('管线已启动')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '启动失败')
  }
}

function canonicalTarget(targetStep) {
  const map = { polish: 'translate_polish', polish_no_translate: 'polish_source' }
  return map[targetStep] || targetStep
}

async function confirmProcessOverwrite(targetStep) {
  const target = canonicalTarget(targetStep)
  const p = store.project
  if (!p) return false
  const messages = []
  if (target === 'transcribe' && (p.segment_count || 0) > 0) {
    messages.push('重新识别会替换现有字幕片段，并清空译文、润色和导出文件。')
  }
  if (['translate', 'translate_polish'].includes(target) && (p.translated_count || 0) > 0) {
    messages.push('重新翻译会覆盖未手工编辑的已有译文，并清空导出文件。')
  }
  if (['polish_source', 'translate_polish'].includes(target) && (p.polished_count || 0) > 0) {
    messages.push('重新润色会覆盖未手工编辑的已有润色文本，并清空导出文件。')
  }
  if (!messages.length) return true
  try {
    await ElMessageBox.confirm(messages.join('\n'), '确认重新处理', { type: 'warning' })
    return true
  } catch {
    return false
  }
}

async function handleCancel() {
  try {
    await cancelSubtitleProcess(store.currentProjectId)
    ElMessage.info('取消请求已发送')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '取消失败')
  }
}

async function handleExport() {
  exporting.value = true
  try {
    await exportSubtitles(store.currentProjectId, { format: exportFormat.value, variant: exportVariant.value })
    ElMessage.success('导出成功')
    await refreshProject()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  } finally {
    exporting.value = false
  }
}

async function handleDownload(out) {
  try {
    const resp = await downloadSubtitleOutput(store.currentProjectId, out.id)
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `subtitle.${out.format}`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('下载失败')
  }
}

function statusType(status) {
  const map = { draft: 'info', uploaded: '', audio_extracted: 'warning', transcribed: 'warning', translated: 'success', polished: 'success', completed: 'success', failed: 'danger', canceled: 'warning' }
  return map[status] || 'info'
}

function statusLabel(status) {
  const map = { draft: '草稿', uploaded: '已上传', audio_extracted: '已提取', transcribed: '已识别', translated: '已翻译', polished: '已润色', completed: '完成', failed: '失败', canceled: '已取消' }
  return map[status] || status
}

function variantLabel(v) {
  const map = { original: '原文', translated: '译文', bilingual: '双语', polished: '润色' }
  return map[v] || v
}
</script>

<style scoped>
.subtitle-view {
  display: flex; gap: 24px; min-height: calc(100vh - 200px);
}
.project-list {
  width: 280px; flex-shrink: 0; padding: 16px;
  display: flex; flex-direction: column; max-height: calc(100vh - 200px);
}
.list-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.list-header h3 { margin: 0; font-size: 15px; font-weight: 700; }
.list-body { flex: 1; overflow-y: auto; }
.project-item {
  padding: 10px 12px; border-radius: 8px; cursor: pointer; margin-bottom: 4px;
  transition: background 0.2s;
}
.project-item:hover { background: #f8fafc; }
.project-item.active { background: var(--el-color-primary-light-9); }
.project-name { font-weight: 600; font-size: 13px; color: #0f172a; margin-bottom: 4px; }
.project-meta { display: flex; align-items: center; gap: 8px; }
.meta-text { font-size: 11px; color: #94a3b8; }
.list-footer { margin-top: 12px; text-align: center; }

.project-detail { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
.detail-header { padding: 16px 20px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.header-row h2 { margin: 0; font-size: 18px; font-weight: 700; flex: 1; }
.header-actions { display: flex; gap: 8px; }

.section-card { padding: 16px 20px; }
.section-card h4 { margin: 0 0 12px; font-size: 14px; font-weight: 600; color: #0f172a; }

.table-section { flex: 1; display: flex; flex-direction: column; min-height: 300px; }
.table-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.table-header h4 { margin: 0; }

.export-form { display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
.outputs-list { border-top: 1px solid #f1f5f9; padding-top: 8px; }
.output-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; font-size: 13px; color: #64748b; }
</style>
