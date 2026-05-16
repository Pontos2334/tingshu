<template>
  <div class="workbench">
    <div class="workbench-grid">
      <section class="surface-card workbench-main">
        <div class="card-header">
          <div>
            <h2>创作与文本</h2>
            <p>同一页里完成取材、改稿、合成，不再来回跳。</p>
          </div>
          <div class="header-actions">
            <el-button @click="loadGenerationHistory" :loading="historyLoading">刷新历史</el-button>
            <el-button @click="openTemplateDrawer()">模板管理</el-button>
          </div>
        </div>

        <el-tabs v-model="sourceTab" class="source-tabs">
          <el-tab-pane label="直接输入" name="draft">
            <div class="source-hint">把待合成文本直接贴进下面的编辑区，右侧配置会一直保留。</div>
          </el-tab-pane>

          <el-tab-pane label="AI 创作" name="ai">
            <el-form label-position="top" class="ai-panel">
              <div class="compact-grid">
                <el-form-item label="模板" class="compact-item">
                  <el-select v-model="aiForm.templateId" placeholder="选择模板" clearable style="width: 100%">
                    <el-option v-for="item in templates" :key="item.id" :label="item.name" :value="item.id" />
                  </el-select>
                </el-form-item>
                <el-form-item label="模型" class="compact-item">
                  <el-select v-model="aiForm.model" style="width: 100%">
                    <el-option label="DeepSeek Chat" value="deepseek-chat" />
                    <el-option label="DeepSeek Reasoner" value="deepseek-reasoner" />
                    <el-option label="DeepSeek V4 Pro" value="deepseek-v4-pro" />
                  </el-select>
                </el-form-item>
              </div>

              <el-form-item label="主题">
                <el-input
                  v-model="aiForm.topic"
                  type="textarea"
                  :rows="3"
                  placeholder="例如：一部带悬疑色彩的唐末历史故事"
                />
              </el-form-item>

              <div v-if="!aiForm.templateId" class="ai-custom-prompts">
                <el-form-item label="系统提示词">
                  <el-input
                    v-model="aiForm.systemPrompt"
                    type="textarea"
                    :rows="3"
                    placeholder="AI 角色与写作要求"
                  />
                </el-form-item>
                <el-form-item label="用户提示词">
                  <el-input
                    v-model="aiForm.userPrompt"
                    type="textarea"
                    :rows="3"
                    placeholder="使用 {topic} 作为主题占位符"
                  />
                </el-form-item>
              </div>

              <div class="compact-grid">
                <el-form-item label="最大字数" class="compact-item">
                  <el-input-number v-model="aiForm.maxTokens" :min="500" :max="8000" :step="500" style="width: 100%" />
                </el-form-item>
                <el-form-item label="思考模式" class="compact-item">
                  <div class="switch-field">
                    <el-switch v-model="aiForm.thinkingEnabled" />
                    <el-radio-group v-if="aiForm.thinkingEnabled" v-model="aiForm.reasoningEffort" size="small">
                      <el-radio-button value="high">高</el-radio-button>
                      <el-radio-button value="max">最高</el-radio-button>
                    </el-radio-group>
                  </div>
                </el-form-item>
              </div>

              <div class="panel-actions">
                <el-button type="primary" :loading="generating" @click="handleGenerate">生成并写入编辑区</el-button>
                <el-button type="success" :loading="generating || synthLoading" @click="handleGenerateAndSynthesize">直接合成</el-button>
                <el-button @click="saveCurrentPromptAsTemplate">存为模板</el-button>
              </div>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="历史生成稿" name="history">
            <div v-if="historyError" class="inline-state">
              <span>{{ historyError }}</span>
              <el-button link type="primary" @click="loadGenerationHistory">重试</el-button>
            </div>
            <el-table v-else :data="generationHistory" size="small" empty-text="还没有生成历史" style="width: 100%">
              <el-table-column prop="topic" label="主题" min-width="260" show-overflow-tooltip />
              <el-table-column prop="model" label="模型" width="150" />
              <el-table-column label="时间" width="160">
                <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="190" fixed="right">
                <template #default="{ row }">
                  <el-button size="small" @click="useHistoryDraft(row)">使用</el-button>
                  <el-button size="small" type="danger" @click="handleDeleteHistory(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>

        <div class="editor-toolbar">
          <div class="editor-meta">当前正文：<strong>{{ workflow.draftText.length }}</strong> 字</div>
          <el-button link type="danger" @click="workflow.setDraftText('')">清空文本</el-button>
        </div>

        <el-input
          :model-value="workflow.draftText"
          type="textarea"
          :rows="18"
          resize="none"
          class="editor-input"
          placeholder="这里是当前准备合成的正文。AI 生成、历史稿件、直接输入都会汇到这一份草稿里。"
          @update:model-value="workflow.setDraftText($event)"
        />
      </section>

      <aside class="workbench-side">
        <section class="surface-card config-section">
          <div class="card-header">
            <div>
              <h2>合成配置</h2>
              <p>设置音色与分段策略。</p>
            </div>
          </div>

          <el-form label-position="top" class="config-form">
            <el-form-item label="音色">
              <el-select v-model="voiceSelection" placeholder="选择音色" style="width: 100%">
                <el-option-group label="预置音色">
                  <el-option v-for="voice in presets" :key="voice.name" :label="voice.name" :value="voice.name">
                    {{ voice.name }} ({{ voice.language }} {{ voice.gender }})
                  </el-option>
                </el-option-group>
                <el-option-group v-if="customVoices.length" label="我的音色">
                  <el-option
                    v-for="voice in customVoices"
                    :key="voice.id"
                    :label="voice.name"
                    :value="`custom-${voice.id}`"
                  >
                    {{ voice.name }} ({{ voice.type === 'design' ? '设计' : '克隆' }})
                  </el-option>
                </el-option-group>
              </el-select>
            </el-form-item>

            <el-form-item label="风格">
              <el-select :model-value="workflow.styles" multiple collapse-tags collapse-tags-tooltip style="width: 100%" @update:model-value="workflow.setStyles($event)">
                <el-option v-for="style in styleOptions" :key="style" :label="style" :value="style" />
              </el-select>
            </el-form-item>

            <el-form-item label="分段长度">
              <el-slider :model-value="workflow.chunkSize" :min="200" :max="1200" :step="100" @update:model-value="workflow.setChunkSize($event)" />
            </el-form-item>

            <div class="panel-actions stack">
              <el-button type="primary" size="large" :loading="synthLoading" @click="handleSynthesize">开始合成任务</el-button>
              <el-button size="large" plain :loading="previewing" @click="handlePreview">试听前 100 字</el-button>
            </div>
          </el-form>
        </section>

        <section class="surface-card task-section">
          <div class="card-header">
            <div>
              <h2 class="section-title">合成任务</h2>
              <p class="section-subtitle">{{ taskStatusLabel }}</p>
            </div>
            <el-button v-if="workflow.currentTaskId" link type="primary" @click="restoreTask">刷新</el-button>
          </div>

          <el-alert
            v-if="workflow.sseReconnecting"
            title="正在重连..."
            type="warning"
            :closable="false"
            show-icon
            class="sse-banner"
          />

          <el-empty v-if="!workflow.taskSnapshot" description="没有正在进行的任务" :image-size="60" />

          <template v-else>
            <div class="task-info">
              <div class="info-row">
                <span>进度</span>
                <strong>{{ workflow.taskSnapshot.completed_chunks || 0 }} / {{ workflow.taskSnapshot.total_chunks || 0 }}</strong>
              </div>
            </div>

            <div class="chunk-scroll">
              <div v-for="chunk in taskChunks" :key="chunk.chunk_index" class="chunk-row">
                <div class="chunk-meta">
                  <span class="chunk-idx">#{{ chunk.chunk_index + 1 }}</span>
                  <span class="chunk-status-tag" :class="chunk.status">{{ chunkLabel(chunk) }}</span>
                </div>
                <el-progress 
                  :percentage="chunk.status === 'completed' ? 100 : 0" 
                  :status="chunk.status === 'failed' ? 'exception' : (chunk.status === 'completed' ? 'success' : '')" 
                  :stroke-width="4" 
                  :show-text="false"
                />
              </div>
            </div>

            <div class="task-actions">
              <el-button v-if="workflow.taskSnapshot.status === 'running'" type="warning" size="small" plain @click="handleCancelTask">取消</el-button>
              <el-button v-if="['failed', 'partial'].includes(workflow.taskSnapshot.status)" type="primary" size="small" @click="handleResumeTask">继续</el-button>
              <el-button v-if="playableTaskRecordIds.length" type="success" size="small" @click="playTaskQueue">播放</el-button>
            </div>
          </template>
        </section>

        <section class="surface-card recent-section">
          <div class="card-header">
            <div>
              <h2 class="section-title">最近草稿</h2>
              <p class="section-subtitle">本地保留 8 份历史记录</p>
            </div>
          </div>
          <el-empty v-if="!workflow.recentOutputs.length" description="空空如也" :image-size="60" />
          <div v-else class="recent-list">
            <button v-for="item in workflow.recentOutputs" :key="item.id || item.createdAt" class="recent-item" @click="useRecentOutput(item)">
              <span class="recent-title">{{ item.topic || '未命名草稿' }}</span>
              <span class="recent-meta">{{ item.model }} · {{ formatDate(item.createdAt) }}</span>
            </button>
          </div>
        </section>
      </aside>
    </div>

    <el-drawer v-model="templateDrawerOpen" size="760px" title="模板管理">
      <div class="template-drawer">
        <div class="template-list">
          <div class="surface-actions">
            <el-button type="primary" @click="createNewTemplate">新建模板</el-button>
          </div>
          <el-table :data="templates" size="small" empty-text="还没有模板">
            <el-table-column prop="name" label="名称" min-width="140" />
            <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
            <el-table-column label="默认" width="70">
              <template #default="{ row }">
                <el-tag v-if="row.is_default" size="small" type="success">默认</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160">
              <template #default="{ row }">
                <el-button size="small" @click="editTemplate(row)">编辑</el-button>
                <el-button size="small" type="danger" :disabled="row.is_default" @click="deleteTemplateItem(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="template-editor">
          <h3>{{ templateDraft.id ? '编辑模板' : '新建模板' }}</h3>
          <el-form label-position="top">
            <el-form-item label="名称">
              <el-input v-model="templateDraft.name" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="templateDraft.description" />
            </el-form-item>
            <el-form-item label="系统提示词">
              <el-input v-model="templateDraft.systemPrompt" type="textarea" :rows="4" />
            </el-form-item>
            <el-form-item label="用户提示词">
              <el-input v-model="templateDraft.userPromptTemplate" type="textarea" :rows="4" />
            </el-form-item>
            <el-form-item label="风格参考">
              <el-input v-model="templateDraft.styleExample" type="textarea" :rows="7" />
            </el-form-item>
          </el-form>
          <div class="panel-actions">
            <el-button @click="createNewTemplate">清空</el-button>
            <el-button type="primary" @click="saveTemplateDraft">保存模板</el-button>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  createTemplate,
  deleteGeneration,
  deleteTemplate,
  generateContent,
  getGenerationHistory,
  getTemplates,
  updateTemplate,
} from '../api/ai'
import { preview, synthesize, createSynthesisTask, getSynthesisTask, resumeSynthesisTask, retryFailedChunks, cancelSynthesisTask } from '../api/tts'
import { getCustomVoices, getPresets } from '../api/voices'
import { friendlyError } from '../api/index'
import { formatDate } from '../utils/format'
import { usePlayerStore } from '../stores/player'
import { useSettingsStore } from '../stores/settings'
import { useWorkflowStore } from '../stores/workflow'

const router = useRouter()
const player = usePlayerStore()
const settingsStore = useSettingsStore()
const workflow = useWorkflowStore()

const sourceTab = ref('draft')
const generating = ref(false)
const synthLoading = ref(false)
const previewing = ref(false)
const historyLoading = ref(false)
const historyError = ref('')
const templateDrawerOpen = ref(false)
const presets = ref([])
const customVoices = ref([])
const templates = ref([])
const generationHistory = ref([])

const aiForm = reactive({
  templateId: '',
  topic: '',
  systemPrompt: '',
  userPrompt: '',
  maxTokens: 4000,
  model: 'deepseek-chat',
  thinkingEnabled: false,
  reasoningEffort: 'high',
})

const templateDraft = reactive({
  id: null,
  name: '',
  description: '',
  systemPrompt: '',
  userPromptTemplate: '',
  styleExample: '',
})

const styleOptions = [
  '开心', '悲伤', '愤怒', '平静', '温柔', '活泼', '严肃', '慵懒',
  '磁性', '甜美', '沙哑', '东北话', '四川话', '粤语', '悄悄话',
]

const taskChunks = computed(() => workflow.taskSnapshot?.chunks || [])
const playableTaskRecordIds = computed(() =>
  taskChunks.value
    .filter(chunk => chunk.audio_record_id)
    .sort((a, b) => a.chunk_index - b.chunk_index)
    .map(chunk => ({
      id: chunk.audio_record_id,
      title: workflow.taskSnapshot?.title || '长文本合成结果',
      sourceType: 'record',
    }))
)

const taskStatusLabel = computed(() => {
  const status = workflow.taskSnapshot?.status
  const map = {
    pending: '等待后端接手',
    running: '后台正在合成',
    completed: '任务已完成',
    failed: '任务失败',
    partial: '部分完成，允许恢复',
    canceled: '任务已取消',
  }
  return map[status] || '还没有任务'
})

const voiceSelection = computed({
  get() {
    return workflow.selectedVoice || settingsStore.defaultVoice || '冰糖'
  },
  set(value) {
    if (value && value.startsWith('custom-')) {
      workflow.setVoiceSelection(value, Number(value.replace('custom-', '')))
      return
    }
    workflow.setVoiceSelection(value, null)
  },
})

let eventSource = null
let reconnectAttempts = 0
let reconnectTimer = null
const MAX_RECONNECTS = 5

onMounted(async () => {
  await Promise.all([
    settingsStore.loadSettings(),
    loadVoices(),
    loadTemplates(),
    loadGenerationHistory(),
  ])

  if (!workflow.selectedVoice) {
    workflow.setVoiceSelection(settingsStore.defaultVoice || '冰糖', null)
  }

  await restoreTask()
})

onBeforeUnmount(() => {
  clearTimeout(reconnectTimer)
  closeSse()
})

async function loadVoices() {
  try {
    const [presetRes, customRes] = await Promise.all([getPresets(), getCustomVoices()])
    presets.value = presetRes.data
    customVoices.value = customRes.data
  } catch (error) {
    ElMessage.error(friendlyError(error, '加载音色失败'))
  }
}

async function loadTemplates() {
  try {
    const { data } = await getTemplates()
    templates.value = data
  } catch (error) {
    ElMessage.error(friendlyError(error, '加载模板失败'))
  }
}

async function loadGenerationHistory() {
  historyLoading.value = true
  historyError.value = ''
  try {
    const { data } = await getGenerationHistory({ page: 1, size: 10 })
    generationHistory.value = data.items || []
  } catch (error) {
    historyError.value = error.response?.data?.detail || '加载生成历史失败'
  } finally {
    historyLoading.value = false
  }
}

function buildGeneratePayload() {
  const payload = {
    topic: aiForm.topic.trim(),
    max_tokens: aiForm.maxTokens,
    model: aiForm.model,
    thinking_enabled: aiForm.thinkingEnabled,
    reasoning_effort: aiForm.reasoningEffort,
  }

  if (aiForm.templateId) {
    payload.template_id = aiForm.templateId
  } else {
    if (aiForm.systemPrompt) payload.system_prompt = aiForm.systemPrompt
    if (aiForm.userPrompt) payload.user_prompt = aiForm.userPrompt
  }

  return payload
}

async function generateDraft() {
  if (!aiForm.topic.trim()) {
    ElMessage.warning('请先输入创作主题')
    return null
  }

  const { data } = await generateContent(buildGeneratePayload())
  workflow.setDraftText(data.generated_text || '')
  workflow.addRecentOutput({
    id: data.id,
    topic: data.topic,
    text: data.generated_text,
    model: data.model,
    createdAt: data.created_at,
  })
  await loadGenerationHistory()
  sourceTab.value = 'draft'
  return data
}

async function handleGenerate() {
  generating.value = true
  try {
    const result = await generateDraft()
    if (result) {
      ElMessage.success('草稿已经写入编辑区')
    }
  } catch (error) {
    ElMessage.error(friendlyError(error, '生成失败'))
  } finally {
    generating.value = false
  }
}

async function handleGenerateAndSynthesize() {
  generating.value = true
  try {
    const result = await generateDraft()
    if (result) {
      ElMessage.success('生成完成，开始合成')
      await startSynthesis(result.generated_text)
    }
  } catch (error) {
    ElMessage.error(friendlyError(error, '操作失败'))
  } finally {
    generating.value = false
  }
}

function buildSynthesisPayload(text) {
  const payload = {
    text,
    voice: voiceSelection.value.startsWith?.('custom-') ? null : voiceSelection.value,
    voice_id: workflow.selectedVoiceId,
    styles: workflow.styles,
  }
  return payload
}

async function handlePreview() {
  const text = workflow.draftText.trim()
  if (!text) {
    ElMessage.warning('请先准备好正文')
    return
  }

  previewing.value = true
  try {
    const { data } = await preview(buildSynthesisPayload(text))
    const startedPlayback = await player.playBlob(data, {
      title: `${voiceSelection.value} 试听`,
      sourceType: 'preview',
      requireVisible: true,
    })
    if (!startedPlayback) {
      ElMessage.success('试听已准备好，回到页面后可直接点底部播放器播放')
    }
  } catch (error) {
    ElMessage.error(friendlyError(error, '试听失败'))
  } finally {
    previewing.value = false
  }
}

async function handleSynthesize() {
  const text = workflow.draftText.trim()
  if (!text) {
    ElMessage.warning('请先准备好正文')
    return
  }

  await startSynthesis(text)
}

async function startSynthesis(text) {
  synthLoading.value = true
  try {
    if (text.length <= 200) {
      const { data } = await synthesize(buildSynthesisPayload(text))
      player.setQueue([{ id: data.id, title: data.title, sourceType: 'record' }], { label: '单条合成结果' })
      const startedPlayback = await player.playWhenVisible({ id: data.id, title: data.title, sourceType: 'record' })
      ElMessage.success(startedPlayback ? '合成成功，已经送入播放器' : '合成成功，结果已加入播放器')
      workflow.clearTaskState()
      return
    }

    const { data } = await createSynthesisTask({
      ...buildSynthesisPayload(text),
      chunk_size: workflow.chunkSize,
    })

    workflow.setTaskState(data.task_id, {
      task_id: data.task_id,
      title: `${text.slice(0, 40)}${text.length > 40 ? '...' : ''}`,
      total_chunks: data.total_chunks,
      completed_chunks: 0,
      failed_chunks: 0,
      status: 'pending',
      chunks: [],
    })
    connectSse(data.task_id)
    ElMessage.success(`长文本任务已创建，共 ${data.total_chunks} 段`)
  } catch (error) {
    ElMessage.error(friendlyError(error, '合成失败'))
  } finally {
    synthLoading.value = false
  }
}

function closeSse() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

function connectSse(taskId) {
  closeSse()
  reconnectAttempts = 0
  openSseConnection(taskId)
}

function openSseConnection(taskId) {
  eventSource = new EventSource(`/api/tts/tasks/${taskId}/events`)
  workflow.setSseState(false, reconnectAttempts > 0)

  eventSource.onopen = () => {
    reconnectAttempts = 0
    workflow.setSseState(true, false)
  }

  eventSource.onmessage = ({ data }) => {
    try {
      const payload = JSON.parse(data)
      void handleTaskEvent(payload)
    } catch {
      // ignore malformed payload
    }
  }

  eventSource.onerror = () => {
    if (eventSource.readyState === EventSource.CONNECTING) {
      workflow.setSseState(false, true)
      reconnectAttempts++
      if (reconnectAttempts > MAX_RECONNECTS) {
        closeSse()
        workflow.setSseState(false, false)
        ElMessage.warning('连接中断已达上限，请点击"刷新状态"重试')
      }
      return
    }
    closeSse()
    workflow.setSseState(false, false)
  }
}

async function handleTaskEvent(payload) {
  if (payload.type === 'snapshot') {
    workflow.updateTaskSnapshot({
      ...payload.task,
      chunks: payload.chunks || [],
      is_running: payload.is_running,
    })
    return
  }

  const snapshot = workflow.taskSnapshot ? { ...workflow.taskSnapshot } : { task_id: workflow.currentTaskId, chunks: [] }
  const chunks = [...(snapshot.chunks || [])]

  if (payload.type === 'chunk_started') {
    const target = chunks.find(item => item.chunk_index === payload.chunk_index)
    if (target) {
      target.status = 'running'
      target.error_message = null
    }
  }

  if (payload.type === 'chunk_retry') {
    const target = chunks.find(item => item.chunk_index === payload.chunk_index)
    if (target) {
      target.status = 'running'
    }
  }

  if (payload.type === 'chunk_done') {
    const target = chunks.find(item => item.chunk_index === payload.chunk_index)
    if (target) {
      target.status = 'completed'
      target.audio_record_id = payload.record_id
      target.error_message = null
    }
    snapshot.completed_chunks = (snapshot.completed_chunks || 0) + 1
  }

  if (payload.type === 'chunk_failed') {
    const target = chunks.find(item => item.chunk_index === payload.chunk_index)
    if (target) {
      target.status = 'failed'
      target.error_message = payload.error
    }
    snapshot.failed_chunks = (snapshot.failed_chunks || 0) + 1
  }

  if (payload.type === 'task_started') {
    snapshot.status = 'running'
  }

  if (payload.type === 'task_done') {
    snapshot.status = payload.status
    snapshot.record_ids = payload.record_ids || []
    closeSse()
    let startedPlayback = false
    if (payload.record_ids?.length) {
      player.setQueue(
        payload.record_ids.map(id => ({ id, title: snapshot.title, sourceType: 'record' })),
        { label: '长文本合成结果' }
      )
      startedPlayback = await player.playWhenVisible({
        id: payload.record_ids[0],
        title: snapshot.title,
        sourceType: 'record',
      })
    }
    if (!startedPlayback && payload.record_ids?.length) {
      ElMessage.success(payload.failed ? '任务完成，但有失败段，结果已加入播放队列' : '长文本合成完成，结果已加入播放队列')
    } else {
      ElMessage.success(payload.failed ? '任务完成，但有失败段' : '长文本合成完成')
    }
  }

  if (payload.type === 'task_canceled') {
    snapshot.status = 'canceled'
    closeSse()
    ElMessage.info('任务已取消')
  }

  if (payload.type === 'task_error') {
    snapshot.status = 'failed'
    closeSse()
    ElMessage.error(payload.error || '任务失败')
  }

  snapshot.chunks = chunks
  workflow.updateTaskSnapshot(snapshot)
}

async function restoreTask() {
  if (!workflow.currentTaskId) return
  try {
    const { data } = await getSynthesisTask(workflow.currentTaskId)
    workflow.updateTaskSnapshot(data)
    if (data.is_running || data.status === 'pending' || data.status === 'running') {
      connectSse(workflow.currentTaskId)
    }
  } catch (error) {
    if (error.response?.status === 404) {
      workflow.clearTaskState()
      ElMessage.info('任务已不存在，已清除本地状态')
    } else {
      ElMessage.warning('刷新任务状态失败，请稍后重试')
    }
  }
}

async function handleCancelTask() {
  if (!workflow.currentTaskId) return
  try {
    await ElMessageBox.confirm('确认取消当前长文本任务？', '取消任务')
    await cancelSynthesisTask(workflow.currentTaskId)
    await restoreTask()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(friendlyError(error, '取消失败'))
    }
  }
}

async function handleResumeTask() {
  if (!workflow.currentTaskId) return
  try {
    await resumeSynthesisTask(workflow.currentTaskId)
    ElMessage.success('任务已恢复')
    await restoreTask()
    connectSse(workflow.currentTaskId)
  } catch (error) {
    ElMessage.error(friendlyError(error, '恢复失败'))
  }
}

async function handleRetryFailed() {
  if (!workflow.currentTaskId) return
  try {
    await retryFailedChunks(workflow.currentTaskId)
    ElMessage.success('失败段已重新排队')
    await restoreTask()
    connectSse(workflow.currentTaskId)
  } catch (error) {
    ElMessage.error(friendlyError(error, '重试失败'))
  }
}

function playTaskQueue() {
  if (!playableTaskRecordIds.value.length) return
  player.setQueue(playableTaskRecordIds.value, { label: '长文本合成结果' })
  player.play(playableTaskRecordIds.value[0])
}

function goLibrary() {
  router.push('/library')
}

function chunkLabel(chunk) {
  const labelMap = {
    pending: '待处理',
    running: '处理中',
    completed: '已完成',
    failed: '失败',
  }
  return labelMap[chunk.status] || chunk.status
}

function useRecentOutput(item) {
  workflow.setDraftText(item.text || '')
  if (item.topic) {
    aiForm.topic = item.topic
  }
}

function useHistoryDraft(row) {
  workflow.setDraftText(row.generated_text)
  aiForm.topic = row.topic
  sourceTab.value = 'draft'
}

function copyHistoryDraft(row) {
  workflow.setDraftText(row.generated_text)
  ElMessage.success('已写入编辑区')
}

async function handleDeleteHistory(row) {
  try {
    await ElMessageBox.confirm(`确认删除「${row.topic}」？`, '删除历史')
    await deleteGeneration(row.id)
    ElMessage.success('历史已删除')
    await loadGenerationHistory()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(friendlyError(error, '删除失败'))
    }
  }
}

function openTemplateDrawer(prefill = null) {
  templateDrawerOpen.value = true
  if (prefill) {
    Object.assign(templateDraft, prefill)
  } else if (!templateDraft.id) {
    createNewTemplate()
  }
}

function createNewTemplate() {
  Object.assign(templateDraft, {
    id: null,
    name: '',
    description: '',
    systemPrompt: '',
    userPromptTemplate: '',
    styleExample: '',
  })
}

function editTemplate(row) {
  openTemplateDrawer({
    id: row.id,
    name: row.name,
    description: row.description || '',
    systemPrompt: row.system_prompt,
    userPromptTemplate: row.user_prompt_template,
    styleExample: row.style_example || '',
  })
}

function saveCurrentPromptAsTemplate() {
  const template = templates.value.find(item => item.id === aiForm.templateId)
  openTemplateDrawer({
    id: null,
    name: template?.name ? `${template.name} 副本` : aiForm.topic || '',
    description: template?.description || '',
    systemPrompt: template?.system_prompt || aiForm.systemPrompt || '你是一个专业的有声书内容创作者。请输出纯文本，不要使用 Markdown 格式。',
    userPromptTemplate: template?.user_prompt_template || aiForm.userPrompt || '请以"{topic}"为主题创作一篇适合朗读的内容。',
    styleExample: template?.style_example || '',
  })
}

async function saveTemplateDraft() {
  if (!templateDraft.name.trim()) {
    ElMessage.warning('请输入模板名称')
    return
  }
  if (!templateDraft.systemPrompt.trim() || !templateDraft.userPromptTemplate.trim()) {
    ElMessage.warning('请把系统提示词和用户提示词补完整')
    return
  }

  const payload = {
    name: templateDraft.name.trim(),
    description: templateDraft.description.trim() || null,
    system_prompt: templateDraft.systemPrompt,
    user_prompt_template: templateDraft.userPromptTemplate,
    style_example: templateDraft.styleExample.trim() || null,
  }

  try {
    if (templateDraft.id) {
      await updateTemplate(templateDraft.id, payload)
    } else {
      await createTemplate(payload)
    }
    ElMessage.success('模板已保存')
    await loadTemplates()
    createNewTemplate()
  } catch (error) {
    ElMessage.error(friendlyError(error, '模板保存失败'))
  }
}

async function deleteTemplateItem(row) {
  try {
    await ElMessageBox.confirm(`确认删除模板「${row.name}」？`, '删除模板')
    await deleteTemplate(row.id)
    ElMessage.success('模板已删除')
    await loadTemplates()
    if (templateDraft.id === row.id) {
      createNewTemplate()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(friendlyError(error, '删除失败'))
    }
  }
}
</script>

<style scoped>
.workbench-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.9fr);
  gap: 24px;
  align-items: start;
}

.workbench-main {
  padding: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 20px;
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

.header-actions {
  display: flex;
  gap: 8px;
}

.source-tabs {
  margin-bottom: 20px;
}

.source-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.source-hint {
  color: #94a3b8;
  font-size: 13px;
  background: #f8fafc;
  padding: 12px 16px;
  border-radius: 8px;
}

.ai-panel {
  display: grid;
  gap: 16px;
}

.compact-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.compact-item {
  margin-bottom: 0;
}

.switch-field {
  display: flex;
  align-items: center;
  gap: 12px;
}

.panel-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.panel-actions.stack {
  flex-direction: column;
}

.editor-toolbar {
  margin: 20px 0 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.editor-meta {
  font-size: 13px;
  color: #64748b;
}

.editor-input :deep(.el-textarea__inner) {
  padding: 16px;
  font-family: inherit;
  font-size: 15px;
  line-height: 1.6;
}

.workbench-side {
  display: grid;
  gap: 24px;
}

.config-section,
.task-section,
.recent-section {
  padding: 24px;
}

.task-info {
  margin-bottom: 16px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #64748b;
}

.chunk-scroll {
  max-height: 200px;
  overflow-y: auto;
  margin-bottom: 16px;
  display: grid;
  gap: 12px;
  padding-right: 4px;
}

.chunk-row {
  display: grid;
  gap: 6px;
}

.chunk-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chunk-idx {
  font-size: 12px;
  color: #94a3b8;
  font-family: monospace;
}

.chunk-status-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
}

.chunk-status-tag.completed { color: #10b981; background: #ecfdf5; }
.chunk-status-tag.running { color: #3b82f6; background: #eff6ff; }
.chunk-status-tag.failed { color: #ef4444; background: #fef2f2; }
.chunk-status-tag.pending { color: #94a3b8; background: #f8fafc; }

.task-actions {
  display: flex;
  gap: 8px;
}

.recent-list {
  display: grid;
  gap: 12px;
}

.recent-item {
  background: #f8fafc;
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 12px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
}

.recent-item:hover {
  background: #ffffff;
  border-color: var(--el-color-primary-light-7);
  box-shadow: var(--el-box-shadow-light);
  transform: translateX(4px);
}

.recent-title {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recent-meta {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #94a3b8;
}

.template-drawer {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 24px;
  padding: 0 24px 24px;
}

.inline-state {
  padding: 12px;
  background: #fffbeb;
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #b45309;
}

@media (max-width: 1000px) {
  .workbench-grid {
    grid-template-columns: 1fr;
  }
}
</style>
