<script setup>
import { ref } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'

const store = useItineraryStore()
const adding = ref(false)
const newName = ref('')

function startAdd() {
  adding.value = true
  newName.value = ''
}

async function submitAdd() {
  const name = newName.value.trim()
  if (!name) return
  await store.createArtist(name)
  adding.value = false
  newName.value = ''
}

function cancelAdd() {
  adding.value = false
  newName.value = ''
}

async function remove(id, name) {
  try {
    await ElMessageBox.confirm(`删除艺人「${name}」将同时删除其全部行程，确定吗？`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await store.deleteArtist(id)
  } catch {
    // cancel
  }
}
</script>

<template>
  <div class="artist-bar">
    <div class="artist-list">
      <div
        v-for="artist in store.artists"
        :key="artist.id"
        :class="['artist-chip', { active: artist.id === store.selectedArtistId }]"
        :style="{ borderColor: artist.color }"
        @click="store.selectArtist(artist.id)"
      >
        <span class="dot" :style="{ background: artist.color }"></span>
        <span class="name">{{ artist.name }}</span>
        <span class="count">{{ artist.event_count || 0 }}</span>
        <el-icon class="del" @click.stop="remove(artist.id, artist.name)"><Delete /></el-icon>
      </div>

      <div v-if="adding" class="artist-chip add-mode">
        <el-input
          v-model="newName"
          size="small"
          placeholder="艺人姓名"
          @keyup.enter="submitAdd"
          @blur="submitAdd"
        />
      </div>
      <div v-else class="add-btn" @click="startAdd">
        <el-icon><Plus /></el-icon>
        <span>新增艺人</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.artist-bar {
  margin-bottom: 16px;
  flex-shrink: 0;
}

.artist-list {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.artist-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px 6px 10px;
  background: #fff;
  border: 2px solid #e4e9f2;
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 14px;
}

.artist-chip:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.artist-chip.active {
  background: #f0f7ff;
  border-width: 2px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.name {
  font-weight: 500;
  color: #1d2b4f;
}

.count {
  font-size: 12px;
  color: #9aabbe;
  background: #f0f4fa;
  border-radius: 999px;
  padding: 1px 7px;
}

.del {
  font-size: 13px;
  color: #9aabbe;
  opacity: 0;
  transition: opacity 0.15s;
}

.artist-chip:hover .del {
  opacity: 1;
}

.del:hover {
  color: #e74c3c;
}

.add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 7px 14px;
  color: #2459a9;
  border: 1px dashed #2459a9;
  border-radius: 999px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.add-btn:hover {
  background: #f0f7ff;
}

.add-mode {
  padding: 4px 8px;
}

@media (max-width: 768px) {
  .artist-list {
    gap: 8px;
  }

  .artist-chip {
    padding: 5px 10px 5px 8px;
    font-size: 13px;
  }

  .del {
    opacity: 1;
  }

  .add-btn {
    padding: 6px 12px;
  }
}
</style>
