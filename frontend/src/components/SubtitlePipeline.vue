<template>
  <div class="subtitle-pipeline">
    <div class="steps">
      <div v-for="step in steps" :key="step.key" class="step" :class="stepClass(step.key)">
        <div class="step-dot">{{ stepIndex(step.key) }}</div>
        <div class="step-label">{{ step.label }}</div>
      </div>
    </div>

    <div v-if="store.pipelineRunning" class="progress-section">
      <el-progress :percentage="store.pipelineProgress" :stroke-width="8" />
      <p class="progress-msg">{{ store.pipelineMessage }}</p>
    </div>

    <div v-if="(store.pipelineMessage || projectError) && !store.pipelineRunning" class="status-msg">
      <el-tag :type="statusTagType" size="small">{{ store.pipelineMessage || projectError }}</el-tag>
      <el-collapse v-if="props.project.status === 'failed' && props.project.error_detail" class="error-detail">
        <el-collapse-item title="错误详情" name="detail">
          <pre>{{ props.project.error_detail }}</pre>
        </el-collapse-item>
      </el-collapse>
    </div>

    <div v-if="nextActions.length && !store.pipelineRunning" class="next-actions">
      <span class="next-label">下一步：</span>
      <el-button
        v-for="action in nextActions"
        :key="action.target"
        type="success"
        size="default"
        @click="$emit('process', action.target)"
      >{{ action.label }}</el-button>
    </div>

    <div class="actions">
      <el-select v-model="oneClickTarget" size="default" style="width: 180px" :disabled="store.pipelineRunning">
        <el-option label="仅识别" value="transcribe" />
        <el-option label="仅翻译" value="translate" />
        <el-option label="仅润色原文" value="polish_source" />
        <el-option label="润色+翻译" value="translate_polish" />
      </el-select>
      <el-button
        type="primary"
        @click="$emit('process', oneClickTarget)"
        :loading="store.pipelineRunning"
        :disabled="store.pipelineRunning"
      >
        {{ props.hasSegments ? '处理' : '一键处理' }}
      </el-button>
      <el-button v-if="store.pipelineRunning" type="danger" @click="$emit('cancel')">
        取消
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useSubtitleStore } from '../stores/subtitle'

const props = defineProps({
  project: { type: Object, required: true },
  hasSegments: { type: Boolean, default: false },
})
defineEmits(['process', 'cancel'])

const store = useSubtitleStore()

const oneClickTarget = ref('translate')

const nextActions = computed(() => {
  if (!props.hasSegments) return []
  const actions = []
  if (!props.project.translated_count) actions.push({ label: '翻译', target: 'translate' })
  if (!props.project.polished_count) actions.push({ label: '润色原文', target: 'polish_source' })
  actions.push({ label: props.project.polished_count ? '重新翻译' : '润色+翻译', target: 'translate_polish' })
  return actions
})

const steps = [
  { key: 'extract', label: '提取音频' },
  { key: 'transcribe', label: '语音识别' },
  { key: 'polish', label: '润色' },
  { key: 'translate', label: '翻译' },
]

function stepIndex(key) {
  return steps.findIndex(s => s.key === key) + 1
}

function stepClass(key) {
  if (store.pipelineRunning && store.pipelineStep === key) return 'active'
  if (isStepDone(key)) return 'done'
  return ''
}

function isStepDone(key) {
  if (key === 'extract') return Boolean(props.project.audio_path)
  if (key === 'transcribe') return (props.project.segment_count || 0) > 0
  if (key === 'polish') return (props.project.polished_count || 0) > 0
  if (key === 'translate') return (props.project.translated_count || 0) > 0
  return false
}

const projectError = computed(() => {
  if (props.project.status === 'failed' && props.project.error_message) return `错误: ${props.project.error_message}`
  if (props.project.status === 'canceled') return '已取消'
  return ''
})

const statusTagType = computed(() => {
  if (['completed', 'translated', 'polished', 'transcribed'].includes(props.project.status)) return 'success'
  if (props.project.status === 'failed') return 'danger'
  if (props.project.status === 'canceled') return 'warning'
  return 'info'
})
</script>

<style scoped>
.steps {
  display: flex; gap: 24px; margin-bottom: 16px;
}
.step {
  display: flex; align-items: center; gap: 8px; color: #94a3b8;
}
.step-dot {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
  background: #f1f5f9; color: #94a3b8;
  transition: all 0.3s;
}
.step.done .step-dot { background: var(--el-color-success); color: #fff; }
.step.active .step-dot { background: var(--el-color-primary); color: #fff; animation: pulse 1.5s infinite; }
.step.current .step-dot { background: var(--el-color-primary-light-5); color: var(--el-color-primary); }
.step-label { font-size: 13px; font-weight: 500; }
.step.done .step-label, .step.active .step-label, .step.current .step-label { color: #0f172a; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.progress-section { margin-bottom: 16px; }
.progress-msg { font-size: 12px; color: #64748b; margin-top: 4px; }
.status-msg { margin-bottom: 12px; }
.error-detail { margin-top: 8px; }
.error-detail pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: 12px;
  color: #475569;
}
.next-actions {
  display: flex; gap: 8px; align-items: center; margin-bottom: 12px;
  padding: 12px; background: #f0fdf4; border-radius: 8px; border: 1px solid #bbf7d0;
}
.next-label { font-size: 13px; font-weight: 600; color: #166534; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
