import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { QrCode, RefreshCw, MonitorPlay, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCrawlerStore } from '@/store/crawlerStore'

// noVNC 页面地址:与 WebUI 同主机,6080 端口(compose 已映射)
function getNovncUrl(): string {
  const host = window.location.hostname
  return `http://${host}:6080/vnc.html?autoconnect=true&resize=scale`
}

type QrState = 'checking' | 'ready' | 'empty'

export function LoginPanel() {
  const { t } = useTranslation('login')
  const status = useCrawlerStore((state) => state.status)
  const loginType = useCrawlerStore((state) => state.config.login_type)
  const [dismissed, setDismissed] = useState(false)
  const [imgTick, setImgTick] = useState(0)

  const isRunning = status === 'running'
  const needQrLogin = isRunning && loginType === 'qrcode'

  // 运行中每 3s 探测一次二维码是否就绪(200=就绪,404=暂无/过期)
  const { data: qrState, refetch } = useQuery<QrState>({
    queryKey: ['loginQrcode', imgTick],
    queryFn: async () => {
      try {
        const resp = await fetch(`/api/crawler/qrcode?t=${Date.now()}`, {
          cache: 'no-store',
        })
        return resp.ok ? 'ready' : 'empty'
      } catch {
        return 'empty'
      }
    },
    enabled: needQrLogin && !dismissed,
    refetchInterval: 3000,
    retry: false,
  })

  // 爬虫停止/重启后复位弹窗状态
  useEffect(() => {
    if (!isRunning) {
      setDismissed(false)
    }
  }, [isRunning])

  if (!needQrLogin || dismissed) {
    return null
  }

  const handleRefresh = () => {
    setImgTick((tick) => tick + 1)
    refetch()
  }

  const handleOpenBrowser = () => {
    window.open(getNovncUrl(), '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-[90]">
      <div className="bg-cyber-bg-panel border-2 border-cyber-neon-cyan rounded-lg shadow-cyber-card p-6 max-w-sm w-full mx-4 relative">
        {/* Corner decorations */}
        <div className="absolute top-0 left-0 w-6 h-6 border-t-2 border-l-2 border-cyber-neon-cyan" />
        <div className="absolute top-0 right-0 w-6 h-6 border-t-2 border-r-2 border-cyber-neon-cyan" />
        <div className="absolute bottom-0 left-0 w-6 h-6 border-b-2 border-l-2 border-cyber-neon-cyan" />
        <div className="absolute bottom-0 right-0 w-6 h-6 border-b-2 border-r-2 border-cyber-neon-cyan" />

        {/* Close button */}
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="absolute top-3 right-3 text-cyber-text-muted hover:text-cyber-neon-pink transition-colors"
          aria-label={t('close')}
        >
          <X className="w-4 h-4" />
        </button>

        {/* Header */}
        <div className="flex items-center justify-center gap-2 mb-3">
          <QrCode className="w-5 h-5 text-cyber-neon-cyan" />
          <h2 className="text-base font-mono font-bold text-cyber-neon-cyan">
            {t('title')}
          </h2>
        </div>

        {/* QR code area */}
        <div className="flex items-center justify-center bg-black/50 border border-cyber-neon-cyan/30 rounded-lg p-4 mb-3 min-h-[240px]">
          {qrState === 'ready' ? (
            <img
              src={`/api/crawler/qrcode?t=${imgTick}`}
              alt={t('title')}
              className="w-52 h-52 object-contain"
            />
          ) : (
            <div className="text-center space-y-2">
              <div className="text-sm font-mono text-cyber-text-secondary">
                {qrState === 'checking' ? t('checking') : t('notReady')}
              </div>
              {qrState === 'empty' && (
                <div className="text-[11px] font-mono text-cyber-text-muted">
                  {t('notReadyHint')}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="text-center text-[11px] font-mono text-cyber-text-muted mb-4">
          {t('scanHint')}
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <Button
            onClick={handleRefresh}
            variant="outline"
            className="flex-1 font-mono text-xs border-cyber-neon-cyan/50 text-cyber-neon-cyan hover:bg-cyber-neon-cyan/10"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            {t('refresh')}
          </Button>
          <Button
            onClick={handleOpenBrowser}
            className="flex-1 font-mono text-xs bg-cyber-neon-green text-black font-bold hover:bg-cyber-neon-green/90"
          >
            <MonitorPlay className="w-3.5 h-3.5" />
            {t('openBrowser')}
          </Button>
        </div>

        <div className="text-center text-[10px] font-mono text-cyber-text-muted mt-3">
          {t('browserHint')}
        </div>
      </div>
    </div>
  )
}
