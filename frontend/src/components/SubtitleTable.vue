<template>
  <div class="subtitle-table">
    <el-table :data="segments" border stripe height="100%" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="40" />
      <el-table-column label="#" width="50" align="center">
        <template #default="{ row }">{{ row.segment_index + 1 }}</template>
      </el-table-column>
      <el-table-column label="开始" width="95" align="center">
        <template #default="{ row }">
          <span v-if="editingId !== row.id || editingField !== 'start'">{{ formatTime(row.start_time) }}</span>
          <el-input v-else v-model="editValue" size="small" @blur="saveEdit(row)" @keyup.enter="saveEdit(row)" autofocus />
        </template>
      </el-table-column>
      <el-table-column label="结束" width="95" align="center">
        <template #default="{ row }">
          <span v-if="editingId !== row.id || editingField !== 'end'">{{ formatTime(row.end_time) }}</span>
          <el-input v-else v-model="editValue" size="small" @blur="saveEdit(row)" @keyup.enter="saveEdit(row)" autofocus />
        </template>
      </el-table-column>
      <el-table-column label="原文" min-width="200">
        <template #default="{ row }">
          <div v-if="editingId !== row.id || editingField !== 'original'" class="text-cell" @dblclick="startEdit(row, 'original', row.original_text)">
            {{ row.original_text }}
          </div>
          <el-input v-else type="textarea" v-model="editValue" :autosize="{ minRows: 1, maxRows: 4 }" @blur="saveEdit(row)" @keyup.ctrl.enter="saveEdit(row)" autofocus />
        </template>
      </el-table-column>
      <el-table-column label="润色" min-width="200">
        <template #default="{ row }">
          <div v-if="editingId !== row.id || editingField !== 'polished'" class="text-cell polished" @dblclick="startEdit(row, 'polished', row.polished_text || '')">
            {{ row.polished_text || '—' }}
          </div>
          <el-input v-else type="textarea" v-model="editValue" :autosize="{ minRows: 1, maxRows: 4 }" @blur="saveEdit(row)" @keyup.ctrl.enter="saveEdit(row)" autofocus />
        </template>
      </el-table-column>
      <el-table-column label="译文" min-width="200">
        <template #default="{ row }">
          <div v-if="editingId !== row.id || editingField !== 'translated'" class="text-cell translated" @dblclick="startEdit(row, 'translated', row.translated_text || '')">
            {{ row.translated_text || '—' }}
          </div>
          <el-input v-else type="textarea" v-model="editValue" :autosize="{ minRows: 1, maxRows: 4 }" @blur="saveEdit(row)" @keyup.ctrl.enter="saveEdit(row)" autofocus />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { updateSubtitleSegment } from '../api/subtitle'

const props = defineProps({
  projectId: { type: Number, required: true },
  segments: { type: Array, default: () => [] },
})
const emit = defineEmits(['updated'])

const editingId = ref(null)
const editingField = ref('')
const editValue = ref('')

function formatTime(sec) {
  if (sec == null) return '--:--:--'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  const ms = Math.floor((sec % 1) * 1000)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function startEdit(row, field, value) {
  editingId.value = row.id
  editingField.value = field
  editValue.value = value
}

async function saveEdit(row) {
  const field = editingField.value
  const value = editValue.value
  editingId.value = null
  editingField.value = ''

  const fieldMap = { start: 'start_time', end: 'end_time', original: 'original_text', translated: 'translated_text', polished: 'polished_text' }
  const apiField = fieldMap[field]
  if (!apiField) return

  const payload = {}
  if (field === 'start' || field === 'end') {
    payload[apiField] = parseFloat(value) || 0
  } else {
    payload[apiField] = value
  }

  try {
    await updateSubtitleSegment(props.projectId, row.id, payload)
    emit('updated')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

function onSelectionChange() {}
</script>

<style scoped>
.subtitle-table { height: 100%; }
.text-cell {
  cursor: pointer; padding: 4px 0; min-height: 24px;
  white-space: pre-wrap; word-break: break-word; font-size: 13px;
}
.text-cell:hover { background: #f0f9ff; border-radius: 4px; }
.text-cell.translated { color: var(--el-color-primary); }
.text-cell.polished { color: var(--el-color-success); }
</style>
