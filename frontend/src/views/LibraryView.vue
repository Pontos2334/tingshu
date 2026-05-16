<template>
  <div class="library-page">
    <div class="library-grid">
      <section class="surface-card library-main">
        <div class="card-header">
          <div>
            <h2>音频库</h2>
            <p>按长文本分组聚合，先看作品整体，再看分段细节。</p>
          </div>
          <div class="header-actions">
            <el-input v-model="query.keyword" placeholder="搜索标题、音色或正文" clearable class="search-input" @keyup.enter="onSearchEnter" />
            <el-switch v-model="query.favoriteOnly" inline-prompt active-text="收藏" inactive-text="全部" @change="onFilterChange" />
            <el-button @click="reloadGroups" :loading="groupsLoading">刷新</el-button>
          </div>
        </div>

        <div v-if="groupsError" class="inline-state">
          <span>{{ groupsError }}</span>
          <el-button link type="primary" @click="reloadGroups">重试</el-button>
        </div>

        <el-table v-else :data="groups" row-key="group_id" empty-text="还没有音频结果" style="width: 100%">
          <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
          <el-table-column prop="voice_name" label="音色" width="120" />
          <el-table-column label="片段" width="80">
            <template #default="{ row }">{{ row.clip_count }}</template>
          </el-table-column>
          <el-table-column label="时长" width="100">
            <template #default="{ row }">{{ formatDuration(row.total_duration) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openGroup(row.group_id)">详情</el-button>
              <el-button size="small" type="success" @click="playGroup(row.group_id)">播放</el-button>
              <el-button size="small" :disabled="!selectedPlaylistId" :loading="addingGroupId === row.group_id" @click="addGroupToPlaylist(row.group_id)">加入列表</el-button>
              <el-button size="small" link type="danger" @click="deleteGroupItem(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-row">
          <el-pagination
            background
            layout="prev, pager, next, total"
            :total="total"
            :page-size="query.size"
            :current-page="query.page"
            @current-change="handlePageChange"
          />
        </div>
      </section>

      <aside class="library-side">
        <section class="surface-card side-section">
          <div class="card-header">
            <div>
              <h2 class="section-title">播放列表</h2>
              <p class="section-subtitle">管理您的收听清单</p>
            </div>
            <el-button type="primary" size="small" @click="createDialogOpen = true">新建</el-button>
          </div>

          <el-empty v-if="!playlists.length" description="暂无列表" :image-size="60" />

          <div v-else class="playlist-stack">
            <button
              v-for="playlist in playlists"
              :key="playlist.id"
              class="playlist-button"
              :class="{ active: playlist.id === selectedPlaylistId }"
              @click="selectPlaylist(playlist.id)"
            >
              <span class="playlist-name">{{ playlist.name }}</span>
              <span class="playlist-desc">{{ playlist.description || '无描述' }}</span>
            </button>
          </div>
        </section>

        <section v-if="selectedPlaylist" class="surface-card side-section playlist-detail-section">
          <div class="card-header">
            <div>
              <h2 class="section-title">{{ selectedPlaylist.name }}</h2>
              <p class="section-subtitle">{{ playlistTracks.length }} 首曲目</p>
            </div>
            <el-button type="danger" link size="small" @click="deletePlaylistItem(selectedPlaylist)">删除列表</el-button>
          </div>

          <el-table :data="playlistTracks" size="small" empty-text="列表为空" style="width: 100%">
            <el-table-column label="标题" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.audio.title }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button size="small" link @click="playTrack(row.audio)">播放</el-button>
                <el-button size="small" link type="danger" @click="removePlaylistTrack(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>
      </aside>
    </div>

    <el-dialog v-model="createDialogOpen" title="新建播放列表" width="420px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="newPlaylist.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newPlaylist.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogOpen = false">取消</el-button>
        <el-button type="primary" @click="savePlaylist">创建</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="groupDrawerOpen" size="860px" :title="groupDetail?.title || '音频详情'">
      <div v-if="groupDetail" class="group-detail">
        <div class="detail-header-grid">
          <div class="detail-stat">
            <span>音色</span>
            <strong>{{ groupDetail.voice_name || '未记录' }}</strong>
          </div>
          <div class="detail-stat">
            <span>片段数</span>
            <strong>{{ groupDetail.clip_count }}</strong>
          </div>
          <div class="detail-stat">
            <span>总时长</span>
            <strong>{{ formatDuration(groupDetail.total_duration) }}</strong>
          </div>
          <div class="detail-stat">
            <span>来源</span>
            <strong>{{ groupDetail.source_type === 'long_text' ? '长文本' : '单条' }}</strong>
          </div>
        </div>

        <div class="surface-actions detail-actions">
          <el-button type="success" @click="playGroup(groupDetail.group_id)">播放整组</el-button>
          <el-button :disabled="!selectedPlaylistId" :loading="addingGroupId === groupDetail.group_id" @click="addGroupToPlaylist(groupDetail.group_id)">加入当前列表</el-button>
          <el-button type="danger" @click="deleteGroupItem(groupDetail)">删除整组</el-button>
        </div>

        <div class="merge-section">
          <el-button
            v-if="groupDetail.clip_count > 1 && !mergeStatus.merging && !groupDetail.has_merged"
            type="primary"
            @click="handleMerge(groupDetail.group_id)"
          >
            合并为完整音频
          </el-button>

          <el-tag v-if="groupDetail.clip_count <= 1" type="info">单条音频，无需合并</el-tag>

          <div v-if="mergeStatus.merging" class="merge-progress">
            <el-progress :percentage="mergeStatus.progress" :status="mergeStatus.error ? 'exception' : ''" />
            <span class="merge-step">{{ mergeStatus.stepLabel }}</span>
          </div>

          <div v-if="groupDetail.merged_record" class="merged-file-card">
            <div class="merged-file-info">
              <el-tag type="success" size="small">已合并</el-tag>
              <span class="merged-title">{{ groupDetail.merged_record.title }}</span>
              <span class="merged-meta">{{ formatDuration(groupDetail.merged_record.duration) }} · {{ formatFileSize(groupDetail.merged_record.file_size) }}</span>
            </div>
            <div class="merged-file-actions">
              <el-button size="small" type="success" @click="playTrack(groupDetail.merged_record)">播放</el-button>
              <el-button size="small" @click="downloadRecord(groupDetail.merged_record)">下载</el-button>
              <el-button size="small" link type="danger" @click="deleteMerged(groupDetail.group_id)">删除合并文件</el-button>
            </div>
          </div>
        </div>

        <el-table :data="groupDetail.records" empty-text="没有可展示的片段">
          <el-table-column label="序号" width="70">
            <template #default="{ row, $index }">{{ row.chunk_index || row.chunk_index === 0 ? row.chunk_index + 1 : $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
          <el-table-column label="时长" width="100">
            <template #default="{ row }">{{ formatDuration(row.duration) }}</template>
          </el-table-column>
          <el-table-column label="收藏" width="90">
            <template #default="{ row }">
              <el-button text @click="toggleRecordFavorite(row)">{{ row.is_favorite ? '取消收藏' : '收藏' }}</el-button>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280">
            <template #default="{ row }">
              <el-button size="small" @click="playTrack(row)">播放</el-button>
              <el-button size="small" @click="downloadRecord(row)">下载</el-button>
              <el-button size="small" :disabled="!selectedPlaylistId" @click="addRecordToPlaylist(row.id)">加入当前列表</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { addTrack, createPlaylist, deletePlaylist, getPlaylists, getTracks, removeTrack } from '../api/playlists'
import { deleteAudioGroup, getAudioGroup, getAudioGroups, getAudioUrl, toggleFavorite, mergeAudioGroup, getMergeEventsUrl, deleteMergedRecord } from '../api/audio'
import { friendlyError } from '../api/index'
import { formatDate, formatDuration } from '../utils/format'
import { usePlayerStore } from '../stores/player'

const player = usePlayerStore()

const groups = ref([])
const total = ref(0)
const groupsLoading = ref(false)
const groupsError = ref('')

const playlists = ref([])
const selectedPlaylistId = ref(null)
const playlistTracks = ref([])
const createDialogOpen = ref(false)
const groupDrawerOpen = ref(false)
const groupDetail = ref(null)

const mergeStatus = reactive({
  merging: false,
  mergeId: '',
  progress: 0,
  stepLabel: '',
  error: '',
})
let mergeEventSource = null

const query = reactive({
  keyword: '',
  favoriteOnly: false,
  page: 1,
  size: 20,
})

const addingGroupId = ref(null)

let keywordDebounceTimer = null

watch(() => query.keyword, () => {
  clearTimeout(keywordDebounceTimer)
  keywordDebounceTimer = setTimeout(() => {
    query.page = 1
    reloadGroups()
  }, 300)
})

watch(groupDrawerOpen, (open) => {
  if (!open) {
    closeMergeSse()
    mergeStatus.merging = false
  }
})

const newPlaylist = reactive({
  name: '',
  description: '',
})

const selectedPlaylist = computed(() => playlists.value.find(item => item.id === selectedPlaylistId.value) || null)

onMounted(async () => {
  await Promise.all([reloadGroups(), loadPlaylists()])
})

async function reloadGroups() {
  groupsLoading.value = true
  groupsError.value = ''
  try {
    const { data } = await getAudioGroups({
      page: query.page,
      size: query.size,
      q: query.keyword || undefined,
      favorite: query.favoriteOnly ? true : undefined,
    })
    groups.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    groupsError.value = error.response?.data?.detail || '加载音频库失败'
  } finally {
    groupsLoading.value = false
  }
}

async function loadPlaylists() {
  try {
    const { data } = await getPlaylists()
    playlists.value = data
    if (!selectedPlaylistId.value && data.length) {
      await selectPlaylist(data[0].id)
    } else if (selectedPlaylistId.value) {
      await loadPlaylistTracks(selectedPlaylistId.value)
    }
  } catch (error) {
    ElMessage.error(friendlyError(error, '加载播放列表失败'))
  }
}

async function selectPlaylist(playlistId) {
  selectedPlaylistId.value = playlistId
  await loadPlaylistTracks(playlistId)
}

async function loadPlaylistTracks(playlistId) {
  if (!playlistId) {
    playlistTracks.value = []
    return
  }
  try {
    const { data } = await getTracks(playlistId)
    playlistTracks.value = data
  } catch (error) {
    ElMessage.error(friendlyError(error, '加载列表内容失败'))
  }
}

async function savePlaylist() {
  if (!newPlaylist.name.trim()) {
    ElMessage.warning('请先填写列表名称')
    return
  }
  try {
    const { data } = await createPlaylist({
      name: newPlaylist.name.trim(),
      description: newPlaylist.description.trim() || null,
    })
    createDialogOpen.value = false
    newPlaylist.name = ''
    newPlaylist.description = ''
    await loadPlaylists()
    await selectPlaylist(data.id)
    ElMessage.success('播放列表已创建')
  } catch (error) {
    ElMessage.error(friendlyError(error, '创建失败'))
  }
}

async function deletePlaylistItem(playlist) {
  try {
    await ElMessageBox.confirm(`确认删除播放列表「${playlist.name}」？`, '删除列表')
    await deletePlaylist(playlist.id)
    if (selectedPlaylistId.value === playlist.id) {
      selectedPlaylistId.value = null
      playlistTracks.value = []
    }
    await loadPlaylists()
    ElMessage.success('播放列表已删除')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(friendlyError(error, '删除失败'))
    }
  }
}

async function openGroup(groupId) {
  try {
    const { data } = await getAudioGroup(groupId)
    groupDetail.value = data
    groupDrawerOpen.value = true
    mergeStatus.merging = false
    mergeStatus.progress = 0
    mergeStatus.stepLabel = ''
    mergeStatus.error = ''
    mergeStatus.mergeId = ''
  } catch (error) {
    ElMessage.error(friendlyError(error, '加载分组详情失败'))
  }
}

async function playGroup(groupId) {
  const detail = groupDetail.value?.group_id === groupId ? groupDetail.value : (await getAudioGroup(groupId)).data
  if (detail.group_id !== groupId) {
    groupDetail.value = detail
  }
  const queue = detail.records.map(record => ({
    id: record.id,
    title: record.title,
    sourceType: 'record',
  }))
  player.setQueue(queue, { label: detail.title })
  player.play(queue[0])
}

function playTrack(record) {
  player.play({
    id: record.id,
    title: record.title,
    sourceType: 'record',
  })
}

function downloadRecord(record) {
  const link = document.createElement('a')
  link.href = getAudioUrl(record.id)
  link.download = `${record.title || 'audio'}.wav`
  link.click()
}

async function toggleRecordFavorite(record) {
  try {
    await toggleFavorite(record.id)
    await Promise.all([reloadGroups(), groupDetail.value ? openGroup(groupDetail.value.group_id) : Promise.resolve()])
  } catch (error) {
    ElMessage.error(friendlyError(error, '操作失败'))
  }
}

async function addRecordToPlaylist(audioId) {
  if (!selectedPlaylistId.value) {
    ElMessage.warning('请先在右侧选一个播放列表')
    return
  }
  try {
    await addTrack(selectedPlaylistId.value, audioId)
    await loadPlaylistTracks(selectedPlaylistId.value)
    ElMessage.success('已加入当前播放列表')
  } catch (error) {
    ElMessage.error(friendlyError(error, '加入失败'))
  }
}

async function addGroupToPlaylist(groupId) {
  if (!selectedPlaylistId.value) {
    ElMessage.warning('请先在右侧选一个播放列表')
    return
  }
  addingGroupId.value = groupId
  try {
    const detail = groupDetail.value?.group_id === groupId ? groupDetail.value : (await getAudioGroup(groupId)).data
    const results = await Promise.allSettled(
      detail.records.map(record => addTrack(selectedPlaylistId.value, record.id))
    )
    const succeeded = results.filter(r => r.status === 'fulfilled').length
    const failed = results.filter(r => r.status === 'rejected').length
    await loadPlaylistTracks(selectedPlaylistId.value)
    if (failed === 0) {
      ElMessage.success(`已把 ${succeeded} 段加入当前列表`)
    } else {
      ElMessage.warning(`已加入 ${succeeded} 段，${failed} 段失败`)
    }
  } catch (error) {
    ElMessage.error(friendlyError(error, '加入失败'))
  } finally {
    addingGroupId.value = null
  }
}

async function removePlaylistTrack(track) {
  if (!selectedPlaylistId.value) return
  try {
    await removeTrack(selectedPlaylistId.value, track.track_id)
    await loadPlaylistTracks(selectedPlaylistId.value)
    ElMessage.success('已从播放列表移除')
  } catch (error) {
    ElMessage.error(friendlyError(error, '移除失败'))
  }
}

async function deleteGroupItem(group) {
  try {
    await ElMessageBox.confirm(`确认删除「${group.title}」整组音频？`, '删除音频组')
    await deleteAudioGroup(group.group_id)
    if (groupDetail.value?.group_id === group.group_id) {
      groupDrawerOpen.value = false
      groupDetail.value = null
    }
    await Promise.all([reloadGroups(), loadPlaylists()])
    ElMessage.success('音频分组已删除')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(friendlyError(error, '删除失败'))
    }
  }
}

function formatFileSize(bytes) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function handleMerge(groupId) {
  mergeStatus.merging = true
  mergeStatus.progress = 0
  mergeStatus.stepLabel = '正在启动合并...'
  mergeStatus.error = ''
  try {
    const { data } = await mergeAudioGroup(groupId)
    mergeStatus.mergeId = data.merge_id
    connectMergeSse(groupId, data.merge_id)
  } catch (error) {
    mergeStatus.merging = false
    ElMessage.error(friendlyError(error, '启动合并失败'))
  }
}

function connectMergeSse(groupId, mergeId) {
  closeMergeSse()
  mergeEventSource = new EventSource(getMergeEventsUrl(groupId, mergeId))

  mergeEventSource.onmessage = ({ data }) => {
    try {
      handleMergeEvent(JSON.parse(data))
    } catch { /* ignore */ }
  }

  mergeEventSource.onerror = () => {
    closeMergeSse()
    if (mergeStatus.merging && !mergeStatus.error) {
      mergeStatus.merging = false
      mergeStatus.error = '连接中断'
    }
  }
}

function closeMergeSse() {
  if (mergeEventSource) {
    mergeEventSource.close()
    mergeEventSource = null
  }
}

function handleMergeEvent(payload) {
  if (payload.type === 'merge_started') {
    mergeStatus.progress = 10
    mergeStatus.stepLabel = `准备中 (共 ${payload.total_chunks} 段)`
  }
  if (payload.type === 'merge_progress') {
    if (payload.step === 'preparing') {
      mergeStatus.progress = Math.round(10 + (payload.current / payload.total) * 40)
      mergeStatus.stepLabel = `验证文件 ${payload.current}/${payload.total}`
    }
    if (payload.step === 'merging') {
      mergeStatus.progress = 60
      mergeStatus.stepLabel = '正在合并音频...'
    }
    if (payload.step === 'saving') {
      mergeStatus.progress = 90
      mergeStatus.stepLabel = '保存中...'
    }
  }
  if (payload.type === 'merge_done') {
    mergeStatus.progress = 100
    mergeStatus.stepLabel = '合并完成'
    mergeStatus.merging = false
    closeMergeSse()
    ElMessage.success('音频合并完成')
    openGroup(groupDetail.value.group_id)
    reloadGroups()
  }
  if (payload.type === 'merge_error') {
    mergeStatus.merging = false
    mergeStatus.error = payload.error
    mergeStatus.stepLabel = '合并失败'
    closeMergeSse()
    ElMessage.error(payload.error || '合并失败')
  }
}

async function deleteMerged(groupId) {
  try {
    await ElMessageBox.confirm('确认删除合并文件？', '删除合并文件')
    await deleteMergedRecord(groupId)
    ElMessage.success('合并文件已删除')
    await openGroup(groupId)
    await reloadGroups()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(friendlyError(error, '删除失败'))
    }
  }
}

function handlePageChange(page) {
  query.page = page
  reloadGroups()
}

function onSearchEnter() {
  clearTimeout(keywordDebounceTimer)
  query.page = 1
  reloadGroups()
}

function onFilterChange() {
  query.page = 1
  reloadGroups()
}
</script>

<style scoped>
.library-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.9fr);
  gap: 24px;
  align-items: start;
}

.library-main {
  padding: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 24px;
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
  gap: 12px;
  align-items: center;
}

.search-input {
  width: 220px;
}

.pagination-row {
  margin-top: 24px;
  display: flex;
  justify-content: flex-end;
}

.library-side {
  display: grid;
  gap: 24px;
}

.side-section {
  padding: 24px;
}

.playlist-stack {
  display: grid;
  gap: 12px;
}

.playlist-button {
  background: #f8fafc;
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 12px 16px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
  display: grid;
  gap: 4px;
}

.playlist-button:hover {
  background: #ffffff;
  border-color: var(--el-color-primary-light-7);
  box-shadow: var(--el-box-shadow-light);
  transform: translateX(4px);
}

.playlist-button.active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}

.playlist-name {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.playlist-desc {
  font-size: 12px;
  color: #94a3b8;
}

.playlist-detail-section {
  border-top: 1px solid #f1f5f9;
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
  margin-bottom: 16px;
}

.group-detail {
  display: grid;
  gap: 24px;
  padding: 0 24px 24px;
}

.detail-header-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.detail-stat {
  background: #f8fafc;
  padding: 16px;
  border-radius: 10px;
  display: grid;
  gap: 4px;
}

.detail-stat span {
  font-size: 12px;
  color: #94a3b8;
}

.detail-stat strong {
  font-size: 16px;
  color: #0f172a;
}

.merge-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: #f8fafc;
  border-radius: 10px;
}

.merge-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.merge-step {
  font-size: 12px;
  color: #64748b;
}

.merged-file-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 8px;
}

.merged-file-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.merged-title {
  font-weight: 600;
  color: #065f46;
}

.merged-meta {
  font-size: 12px;
  color: #6b7280;
}

.merged-file-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 1000px) {
  .library-grid {
    grid-template-columns: 1fr;
  }
}
</style>
