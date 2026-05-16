<template>
  <div class="subtitle-upload">
    <div v-if="!project.video_filename" class="upload-zone" @dragover.prevent @drop.prevent="onDrop">
      <el-icon class="upload-icon"><Upload /></el-icon>
      <p>拖拽视频/音频文件到此处，或</p>
      <el-upload
        :show-file-list="false"
        :before-upload="beforeUpload"
        :http-request="handleUpload"
        accept="video/*,audio/*"
      >
        <el-button type="primary" :loading="uploading">选择文件</el-button>
      </el-upload>
      <p class="upload-hint">视频: mp4, avi, mkv, mov, flv, webm 等 · 音频: mp3, wav, flac, m4a, ogg 等</p>
      <el-progress v-if="uploading" :percentage="uploadProgress" :stroke-width="6" style="margin-top: 12px" />
    </div>
    <div v-else class="file-info">
      <div class="file-meta">
        <el-icon><component :is="isAudioFile(project.video_filename) ? Headset : VideoCamera" /></el-icon>
        <span class="file-name">{{ project.video_filename }}</span>
        <span v-if="project.video_duration" class="file-duration">{{ formatDuration(project.video_duration) }}</span>
        <span v-if="project.video_size" class="file-size">{{ formatSize(project.video_size) }}</span>
      </div>
      <div class="file-actions">
        <el-upload :show-file-list="false" :before-upload="beforeUpload" :http-request="handleUpload" accept="video/*,audio/*">
          <el-button size="small">重新上传</el-button>
        </el-upload>
      </div>
    </div>
    <div class="import-row">
      <el-divider>或</el-divider>
      <el-upload :show-file-list="false" :before-upload="beforeImportSrt" :http-request="handleImportSrt" accept=".srt">
        <el-button :loading="importing">导入已有 SRT 字幕</el-button>
      </el-upload>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, VideoCamera, Headset } from '@element-plus/icons-vue'
import { uploadSubtitleVideo, uploadSubtitleAudio, importSubtitleSrt } from '../api/subtitle'

const props = defineProps({ project: { type: Object, required: true } })
const emit = defineEmits(['updated'])

const uploading = ref(false)
const uploadProgress = ref(0)
const importing = ref(false)

const videoExts = ['mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'm4v', 'mpeg', 'mpg', 'ts']
const audioExts = ['mp3', 'wav', 'flac', 'm4a', 'ogg', 'aac', 'wma', 'opus']

function isAudioFile(filename) {
  const ext = filename.split('.').pop().toLowerCase()
  return audioExts.includes(ext)
}

function formatDuration(sec) {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function formatSize(bytes) {
  if (bytes > 1024 * 1024 * 1024) return (bytes / 1024 / 1024 / 1024).toFixed(1) + ' GB'
  if (bytes > 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  return (bytes / 1024).toFixed(0) + ' KB'
}

function beforeUpload(file) {
  const ext = file.name.split('.').pop().toLowerCase()
  if (!videoExts.includes(ext) && !audioExts.includes(ext)) {
    ElMessage.error('不支持的文件格式')
    return false
  }
  return true
}

async function handleUpload(options) {
  uploading.value = true
  uploadProgress.value = 0
  try {
    const file = options.file
    const ext = file.name.split('.').pop().toLowerCase()
    const isAudio = audioExts.includes(ext)
    const formData = new FormData()
    formData.append('file', file)
    const uploader = isAudio ? uploadSubtitleAudio : uploadSubtitleVideo
    await uploader(props.project.id, formData, (e) => {
      if (e.total) uploadProgress.value = Math.round((e.loaded / e.total) * 100)
    })
    ElMessage.success(isAudio ? '音频上传成功' : '视频上传成功')
    emit('updated')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

function onDrop(e) {
  const file = e.dataTransfer?.files?.[0]
  if (file) handleUpload({ file })
}

function beforeImportSrt(file) {
  if (!file.name.endsWith('.srt')) {
    ElMessage.error('请上传 .srt 文件')
    return false
  }
  return true
}

async function handleImportSrt(options) {
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', options.file)
    await importSubtitleSrt(props.project.id, formData)
    ElMessage.success('SRT 导入成功')
    emit('updated')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.upload-zone {
  border: 2px dashed #d1d5db;
  border-radius: 12px;
  padding: 40px 24px;
  text-align: center;
  color: #64748b;
  transition: border-color 0.2s;
}
.upload-zone:hover { border-color: var(--el-color-primary); }
.upload-icon { font-size: 40px; color: #94a3b8; margin-bottom: 12px; }
.upload-hint { font-size: 12px; color: #94a3b8; margin-top: 8px; }
.file-info {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: #f8fafc; border-radius: 8px;
}
.file-meta { display: flex; align-items: center; gap: 8px; }
.file-name { font-weight: 600; color: #0f172a; }
.file-duration, .file-size { font-size: 12px; color: #94a3b8; }
.import-row { text-align: center; margin-top: 16px; }
:deep(.el-divider__text) { font-size: 12px; color: #94a3b8; }
</style>
