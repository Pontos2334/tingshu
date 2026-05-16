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

    <div v-if="store.pipelineMessage && !store.pipelineRunning" class="status-msg">
      <el-tag :type="statusTagType" size="small">{{ store.pipelineMessage }}</el-tag>
    </div>

    <div class="actions">
      <el-button
        type="primary"
        @click="$emit('process', 'translate')"
        :loading="store.pipelineRunning"
        :disabled="store.pipelineRunning"
      >
        一键处理
      </el-button>
      <el-button @click="$emit('process', 'transcribe')" :disabled="store.pipelineRunning">
        仅识别
      </el-button>
      <el-button @click="$emit('process', 'translate')" :disabled="store.pipelineRunning || !hasSegments">
        仅翻译
      </el-button>
      <el-button v-if="store.pipelineRunning" type="danger" @click="$emit('cancel')">
        取消
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSubtitleStore } from '../stores/subtitle'

const props = defineProps({
  project: { type: Object, required: true },
  hasSegments: { type: Boolean, default: false },
})
defineEmits(['process', 'cancel'])

const store = useSubtitleStore()

const steps = [
  { key: 'extract', label: '提取音频' },
  { key: 'transcribe', label: '语音识别' },
  { key: 'translate', label: '翻译' },
]

const statusOrder = { draft: 0, uploaded: 1, audio_extracted: 2, transcribed: 3, translated: 4, completed: 4 }

function stepIndex(key) {
  return steps.findIndex(s => s.key === key) + 1
}

function stepClass(key) {
  const current = statusOrder[props.project.status] || 0
  const idx = stepIndex(key)
  if (store.pipelineRunning && store.pipelineStep === key) return 'active'
  if (current >= idx + 1) return 'done'
  if (current === idx) return 'current'
  return ''
}

const statusTagType = computed(() => {
  if (props.project.status === 'completed') return 'success'
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
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
