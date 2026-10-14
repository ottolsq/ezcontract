<script setup>
import { onMounted, ref } from 'vue'
import { useItineraryStore } from '../stores/itinerary'
import ArtistSelector from '../components/itinerary/ArtistSelector.vue'
import ItineraryCalendar from '../components/itinerary/ItineraryCalendar.vue'
import VoiceInputButton from '../components/itinerary/VoiceInputButton.vue'
import VoiceConfirmDialog from '../components/itinerary/VoiceConfirmDialog.vue'
import DayDetailDrawer from '../components/itinerary/DayDetailDrawer.vue'

const store = useItineraryStore()
const detailRef = ref(null)

onMounted(async () => {
  store.initMonth()
  await store.fetchArtists()
  if (store.selectedArtistId) {
    await store.fetchMonthEvents()
  }
})
</script>

<template>
  <div class="page itinerary-page">
    <div class="page-head">
      <h1>艺人行程</h1>
      <div class="head-actions">
        <span v-if="store.selectedArtist" class="artist-label" :style="{ color: store.selectedArtist.color }">
          当前：{{ store.selectedArtist.name }}
        </span>
      </div>
    </div>

    <ArtistSelector />

    <div v-if="!store.artists.length" class="empty-state">
      <el-empty description="暂无艺人，请先新增艺人">
        <template #image>
          <div class="empty-icon">🎤</div>
        </template>
      </el-empty>
    </div>

    <template v-else>
      <ItineraryCalendar />
    </template>

    <VoiceInputButton />
    <VoiceConfirmDialog />
    <DayDetailDrawer ref="detailRef" />
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 16px 24px;
}

.itinerary-page {
  overflow-y: visible;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  flex-shrink: 0;
}

h1 {
  margin: 0;
  font-size: 24px;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.artist-label {
  font-size: 14px;
  font-weight: 500;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 16px;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

@media (max-width: 768px) {
  .page {
    padding: 16px;
  }

  h1 {
    font-size: 20px;
  }
}

@media (max-width: 480px) {
  .page {
    padding: 12px;
  }
}
</style>
