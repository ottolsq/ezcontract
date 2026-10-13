<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Menu } from '@element-plus/icons-vue'
import { useAuthStore } from './stores/auth'
import NotificationBell from './components/NotificationBell.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const isFullscreen = computed(() => Boolean(route.meta.fullscreen))

const isMobileMenuOpen = ref(false)
const isMobile = ref(false)

function checkMobile() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) {
    isMobileMenuOpen.value = false
  }
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

async function onLogout() {
  await auth.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <header v-if="!isFullscreen" class="top-bar">
      <span class="brand" @click="router.push('/')">⚖️ 法衡 AI · 企业多智能体工作台</span>

      <nav v-if="auth.isLoggedIn" class="nav desktop-only">
        <router-link to="/draft">合同起草</router-link>
        <router-link to="/review">合同审查</router-link>
        <router-link to="/compliance">履约提醒</router-link>
      </nav>

      <div class="right-area">
        <template v-if="auth.isLoggedIn">
          <NotificationBell class="desktop-only" />
          <span class="user-chip desktop-only">
            <span class="user-avatar">{{ auth.username.charAt(0).toUpperCase() }}</span>
            <span class="user-name">{{ auth.username }}</span>
          </span>
          <el-button class="desktop-only" text @click="onLogout">退出登录</el-button>
          <div class="mobile-menu-toggle mobile-only" @click="isMobileMenuOpen = !isMobileMenuOpen">
            <el-icon><Menu /></el-icon>
          </div>
        </template>
        <el-button v-else type="primary" size="small" @click="router.push('/login')">
          登录
        </el-button>
      </div>
    </header>

    <transition name="slide">
      <nav v-show="isMobileMenuOpen && auth.isLoggedIn" class="mobile-nav mobile-only">
        <router-link to="/draft" @click="isMobileMenuOpen = false">合同起草</router-link>
        <router-link to="/review" @click="isMobileMenuOpen = false">合同审查</router-link>
        <router-link to="/compliance" @click="isMobileMenuOpen = false">履约提醒</router-link>
        <span class="mobile-user-row">
          <span class="user-avatar">{{ auth.username.charAt(0).toUpperCase() }}</span>
          <span class="user-name">{{ auth.username }}</span>
        </span>
        <el-button text @click="onLogout">退出登录</el-button>
      </nav>
    </transition>

    <main :class="['app-main', { 'app-main--full': isFullscreen }]">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.top-bar {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #e4e9f2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  position: sticky;
  top: 0;
  z-index: 10;
}

.app-main {
  height: calc(100vh - 56px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 全屏路由（如 /login）：绕过固定高度，由子页面自己撑满剩余视口 */
.app-main--full {
  flex: 1;
  overflow: hidden;
  display: block;
}

.brand {
  font-weight: 600;
  cursor: pointer;
}

.nav {
  display: flex;
  gap: 22px;
  margin-left: 32px;
  flex: 1;
}

.nav a {
  color: #66758a;
  text-decoration: none;
  font-size: 14px;
}

.nav a.router-link-active {
  color: #2459a9;
  font-weight: 600;
}

.right-area {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px 4px 4px;
  background: #f0f4fa;
  border-radius: 999px;
  font-size: 13px;
  color: #1d2b4f;
}

.user-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #2459a9;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}

.user-name {
  font-weight: 500;
}

.mobile-menu-toggle {
  display: none;
  cursor: pointer;
  font-size: 22px;
  padding: 8px;
  color: #1d2b4f;
}

.mobile-nav {
  position: absolute;
  top: 56px;
  left: 0;
  right: 0;
  background: #fff;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  z-index: 100;
}

.mobile-nav a {
  padding: 8px 0;
  border-bottom: 1px solid #eee;
  color: #66758a;
  text-decoration: none;
  font-size: 15px;
}

.mobile-nav a.router-link-active {
  color: #2459a9;
  font-weight: 600;
}

.mobile-user-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateY(-10px);
  opacity: 0;
}

@media (max-width: 768px) {
  .top-bar {
    flex-wrap: wrap;
    padding: 0 12px;
    position: relative;
  }

  .brand {
    font-size: 14px;
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .mobile-menu-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
  }
}

</style>
