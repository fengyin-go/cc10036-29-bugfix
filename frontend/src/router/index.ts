import { createRouter, createWebHistory } from 'vue-router'

import LineageView from '@/views/LineageView.vue'
import Overview from '@/views/Overview.vue'
import SchedulerView from '@/views/SchedulerView.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    { path: '/query_scheduler', name: 'scheduler', component: SchedulerView },
    { path: '/data_lineage', name: 'lineage', component: LineageView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
