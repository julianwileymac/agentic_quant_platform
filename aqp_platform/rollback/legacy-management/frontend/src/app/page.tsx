'use client'

import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { ClusterOverview } from '@/components/dashboard/ClusterOverview'
import { NodesGrid } from '@/components/dashboard/NodesGrid'
import { ServicesStatus } from '@/components/dashboard/ServicesStatus'
import { HardwareMetrics } from '@/components/dashboard/HardwareMetrics'

export default function Dashboard() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Cluster Dashboard" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-6">
            {/* Cluster Overview */}
            <ClusterOverview />
            
            {/* Nodes Grid */}
            <section>
              <h2 className="text-lg font-semibold text-surface-200 mb-4">
                Cluster Nodes
              </h2>
              <NodesGrid />
            </section>
            
            {/* Two column layout for services and metrics */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Services Status */}
              <section>
                <h2 className="text-lg font-semibold text-surface-200 mb-4">
                  Base Services
                </h2>
                <ServicesStatus />
              </section>
              
              {/* Hardware Metrics */}
              <section>
                <h2 className="text-lg font-semibold text-surface-200 mb-4">
                  Hardware Metrics
                </h2>
                <HardwareMetrics />
              </section>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
