import { useTranslation } from 'react-i18next'
import { useVehicleSelection } from "@/hooks/useVehicleSelection"
import { getSpeedTextClass } from "@/lib/speedColors"

export function VehicleInfoPanel() {
    const { t } = useTranslation()
    const { selectedVehicle, selectVehicle } = useVehicleSelection()

    if (!selectedVehicle) return null

    return (
        <div
            className="absolute bg-white rounded-lg p-3 shadow-lg text-[13px] z-1000 min-w-52 pointer-events-auto whitespace-nowrap"
            style={{
                left: selectedVehicle.screenX + 15,
                top: selectedVehicle.screenY - 10
            }}
        >
            <div className="flex justify-between items-center mb-2">
                <strong className="text-slate-700">{t('map.vehicle.title')}</strong>
                <button
                    onClick={() => selectVehicle(null)}
                    className="bg-transparent border-none cursor-pointer text-slate-400 text-base p-0 leading-none hover:text-slate-600"
                >
                    ×
                </button>
            </div>

            <div className="text-slate-500 leading-relaxed space-y-1">
                <div>
                    <span className="text-slate-400">{t('map.vehicle.detectionSpeed')}</span>{' '}
                    <span className={`font-semibold ${getSpeedTextClass(selectedVehicle.detectionSpeed)}`}>
                        {selectedVehicle.detectionSpeed.toFixed(1)} km/h
                    </span>
                    <span className="text-slate-300 text-xs ml-1">{t('map.vehicle.sensor')}</span>
                </div>
                <div>
                    <span className="text-slate-400">{t('map.vehicle.visualSpeed')}</span>{' '}
                    <span className="font-medium text-slate-600">
                        {selectedVehicle.speed.toFixed(1)} km/h
                    </span>
                    <span className="text-slate-300 text-xs ml-1">{t('map.vehicle.interpolated')}</span>
                </div>
                <div className="pt-1 border-t border-slate-100">
                    <span className="text-slate-400">{`${t('common.channel')}:`}</span>{' '}
                    {selectedVehicle.channel.toFixed(1)}
                </div>
                <div>
                    <span className="text-slate-400">{t('map.vehicle.direction')}</span>{' '}
                    {selectedVehicle.direction === 0 ? `→ ${t('map.vehicle.forward')}` : `← ${t('map.vehicle.backward')}`}
                </div>
            </div>
        </div>
    )
}
