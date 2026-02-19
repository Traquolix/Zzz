import { useRef, useEffect, useMemo } from 'react'
import { format } from 'date-fns'
import type { SpectralTimeSeries } from '@/types/infrastructure'

type Props = {
    data: SpectralTimeSeries
    width?: number
    height?: number
}

// Viridis colormap (256 colors, RGB)
const VIRIDIS: [number, number, number][] = [
    [68, 1, 84], [68, 2, 86], [69, 4, 87], [69, 5, 89], [70, 7, 90],
    [70, 8, 92], [70, 10, 93], [70, 11, 94], [71, 13, 96], [71, 14, 97],
    [71, 16, 99], [71, 17, 100], [71, 19, 101], [72, 20, 103], [72, 22, 104],
    [72, 23, 105], [72, 24, 106], [72, 26, 108], [72, 27, 109], [72, 28, 110],
    [72, 29, 111], [72, 31, 112], [72, 32, 113], [72, 33, 115], [72, 35, 116],
    [72, 36, 117], [72, 37, 118], [72, 38, 119], [72, 40, 120], [72, 41, 121],
    [71, 42, 122], [71, 44, 122], [71, 45, 123], [71, 46, 124], [71, 47, 125],
    [70, 48, 126], [70, 50, 126], [70, 51, 127], [69, 52, 128], [69, 53, 129],
    [69, 55, 129], [68, 56, 130], [68, 57, 131], [68, 58, 131], [67, 60, 132],
    [67, 61, 132], [66, 62, 133], [66, 63, 133], [66, 64, 134], [65, 66, 134],
    [65, 67, 135], [64, 68, 135], [64, 69, 136], [63, 71, 136], [63, 72, 137],
    [62, 73, 137], [62, 74, 137], [62, 76, 138], [61, 77, 138], [61, 78, 138],
    [60, 79, 139], [60, 80, 139], [59, 82, 139], [59, 83, 140], [58, 84, 140],
    [58, 85, 140], [57, 86, 141], [57, 88, 141], [56, 89, 141], [56, 90, 141],
    [55, 91, 142], [55, 92, 142], [54, 94, 142], [54, 95, 142], [53, 96, 142],
    [53, 97, 142], [52, 98, 143], [52, 100, 143], [51, 101, 143], [51, 102, 143],
    [50, 103, 143], [50, 105, 143], [49, 106, 143], [49, 107, 143], [49, 108, 143],
    [48, 109, 143], [48, 111, 143], [47, 112, 143], [47, 113, 143], [46, 114, 143],
    [46, 116, 143], [46, 117, 143], [45, 118, 143], [45, 119, 143], [44, 121, 142],
    [44, 122, 142], [44, 123, 142], [43, 124, 142], [43, 126, 142], [43, 127, 141],
    [42, 128, 141], [42, 129, 141], [42, 131, 140], [41, 132, 140], [41, 133, 140],
    [41, 135, 139], [40, 136, 139], [40, 137, 138], [40, 138, 138], [40, 140, 137],
    [39, 141, 137], [39, 142, 136], [39, 144, 136], [39, 145, 135], [39, 146, 134],
    [38, 148, 134], [38, 149, 133], [38, 150, 132], [38, 152, 131], [38, 153, 131],
    [38, 154, 130], [38, 156, 129], [38, 157, 128], [39, 158, 127], [39, 160, 126],
    [39, 161, 125], [39, 163, 124], [39, 164, 123], [40, 165, 122], [40, 167, 121],
    [40, 168, 120], [41, 169, 119], [41, 171, 118], [42, 172, 117], [42, 174, 116],
    [43, 175, 115], [43, 176, 113], [44, 178, 112], [45, 179, 111], [45, 181, 110],
    [46, 182, 108], [47, 183, 107], [48, 185, 106], [48, 186, 104], [49, 188, 103],
    [50, 189, 102], [51, 190, 100], [52, 192, 99], [53, 193, 97], [54, 195, 96],
    [55, 196, 94], [56, 197, 93], [58, 199, 91], [59, 200, 90], [60, 201, 88],
    [62, 203, 86], [63, 204, 85], [64, 206, 83], [66, 207, 81], [67, 208, 80],
    [69, 210, 78], [71, 211, 76], [72, 212, 74], [74, 214, 72], [76, 215, 71],
    [78, 216, 69], [79, 218, 67], [81, 219, 65], [83, 220, 63], [85, 221, 61],
    [87, 223, 59], [89, 224, 57], [91, 225, 55], [94, 226, 53], [96, 227, 51],
    [98, 229, 49], [100, 230, 47], [103, 231, 45], [105, 232, 43], [107, 233, 41],
    [110, 234, 39], [112, 235, 37], [115, 236, 35], [117, 237, 33], [120, 238, 31],
    [122, 239, 29], [125, 240, 27], [127, 241, 25], [130, 242, 24], [133, 243, 22],
    [135, 244, 21], [138, 245, 19], [141, 245, 18], [143, 246, 17], [146, 247, 16],
    [149, 248, 15], [151, 249, 14], [154, 249, 14], [157, 250, 14], [160, 251, 13],
    [162, 251, 13], [165, 252, 13], [168, 253, 14], [171, 253, 14], [173, 254, 15],
    [176, 254, 16], [179, 255, 17], [182, 255, 18], [185, 255, 19], [187, 255, 21],
    [190, 255, 22], [193, 255, 24], [196, 255, 25], [199, 255, 27], [201, 255, 29],
    [204, 255, 31], [207, 255, 33], [210, 255, 35], [212, 255, 38], [215, 255, 40],
    [218, 255, 42], [220, 255, 45], [223, 255, 47], [226, 255, 50], [228, 255, 53],
    [231, 255, 55], [233, 255, 58], [236, 255, 61], [238, 255, 64], [241, 255, 67],
    [243, 255, 70], [246, 255, 73], [248, 255, 76], [250, 255, 79], [253, 255, 82],
]

function getColor(value: number, min: number, max: number): [number, number, number] {
    if (max === min) return VIRIDIS[0]
    const normalized = Math.max(0, Math.min(1, (value - min) / (max - min)))
    const index = Math.floor(normalized * (VIRIDIS.length - 1))
    return VIRIDIS[Math.max(0, Math.min(index, VIRIDIS.length - 1))] || VIRIDIS[0]
}

export function SpectralHeatmap({ data, width = 800, height = 280 }: Props) {
    const canvasRef = useRef<HTMLCanvasElement>(null)

    // Axis padding
    const padding = { top: 10, right: 10, bottom: 35, left: 45 }
    const plotWidth = width - padding.left - padding.right
    const plotHeight = height - padding.top - padding.bottom

    // Compute min/max for color scaling
    const { minVal, maxVal } = useMemo(() => {
        let min = Infinity
        let max = -Infinity
        for (const row of data.spectra) {
            for (const val of row) {
                if (val < min) min = val
                if (val > max) max = val
            }
        }
        return { minVal: min, maxVal: max }
    }, [data])

    // Compute time ticks
    const timeTicks = useMemo(() => {
        const t0 = new Date(data.t0)
        const durationSec = data.durationSeconds
        const durationHours = durationSec / 3600

        // Determine tick interval
        let tickIntervalHours = 1
        if (durationHours > 72) tickIntervalHours = 12
        else if (durationHours > 24) tickIntervalHours = 6
        else if (durationHours > 12) tickIntervalHours = 3
        else if (durationHours > 6) tickIntervalHours = 2

        const ticks: { x: number; label: string }[] = []
        const startMs = t0.getTime()
        const endMs = startMs + durationSec * 1000

        // Start from the next round hour
        const current = new Date(startMs)
        current.setMinutes(0, 0, 0)
        if (current.getTime() < startMs) {
            current.setHours(current.getHours() + 1)
        }

        // Align to interval
        const startHour = current.getHours()
        const alignedHour = Math.ceil(startHour / tickIntervalHours) * tickIntervalHours
        current.setHours(alignedHour)

        while (current.getTime() <= endMs) {
            if (current.getTime() >= startMs) {
                const offsetRatio = (current.getTime() - startMs) / (endMs - startMs)
                ticks.push({
                    x: padding.left + offsetRatio * plotWidth,
                    label: format(current, 'HH:mm'),
                })
            }
            current.setHours(current.getHours() + tickIntervalHours)
        }

        return ticks
    }, [data, plotWidth, padding.left])

    // Compute frequency ticks
    const freqTicks = useMemo(() => {
        const [minFreq, maxFreq] = data.freqRange
        const range = maxFreq - minFreq

        // Generate ~5 ticks
        const step = range / 4
        const ticks: { y: number; label: string }[] = []

        for (let i = 0; i <= 4; i++) {
            const freq = minFreq + i * step
            const ratio = (freq - minFreq) / range
            // Y is inverted (low freq at bottom)
            const y = padding.top + (1 - ratio) * plotHeight
            ticks.push({
                y,
                label: freq.toFixed(2),
            })
        }

        return ticks
    }, [data, plotHeight, padding.top])

    // Draw heatmap
    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) return

        const ctx = canvas.getContext('2d')
        if (!ctx) return

        const numTime = data.spectra.length
        const numFreq = data.spectra[0]?.length || 0

        // Clear canvas
        ctx.clearRect(0, 0, width, height)

        // Create heatmap ImageData
        const tempCanvas = document.createElement('canvas')
        tempCanvas.width = numTime
        tempCanvas.height = numFreq
        const tempCtx = tempCanvas.getContext('2d')!
        const imageData = tempCtx.createImageData(numTime, numFreq)
        const pixels = imageData.data

        for (let t = 0; t < numTime; t++) {
            for (let f = 0; f < numFreq; f++) {
                const value = data.spectra[t][f]
                const [r, g, b] = getColor(value, minVal, maxVal)
                // Flip y-axis so low frequencies are at bottom
                const yFlipped = numFreq - 1 - f
                const idx = (yFlipped * numTime + t) * 4
                pixels[idx] = r
                pixels[idx + 1] = g
                pixels[idx + 2] = b
                pixels[idx + 3] = 255
            }
        }

        tempCtx.putImageData(imageData, 0, 0)

        // Draw heatmap scaled to plot area
        ctx.imageSmoothingEnabled = false
        ctx.drawImage(tempCanvas, padding.left, padding.top, plotWidth, plotHeight)

        // Draw axes
        ctx.strokeStyle = '#e2e8f0'
        ctx.lineWidth = 1

        // Y-axis
        ctx.beginPath()
        ctx.moveTo(padding.left, padding.top)
        ctx.lineTo(padding.left, padding.top + plotHeight)
        ctx.stroke()

        // X-axis
        ctx.beginPath()
        ctx.moveTo(padding.left, padding.top + plotHeight)
        ctx.lineTo(padding.left + plotWidth, padding.top + plotHeight)
        ctx.stroke()

        // Draw tick marks and labels
        ctx.fillStyle = '#64748b'
        ctx.font = '10px system-ui, sans-serif'

        // Frequency ticks (Y-axis)
        ctx.textAlign = 'right'
        ctx.textBaseline = 'middle'
        for (const tick of freqTicks) {
            // Tick mark
            ctx.beginPath()
            ctx.moveTo(padding.left - 4, tick.y)
            ctx.lineTo(padding.left, tick.y)
            ctx.stroke()
            // Label
            ctx.fillText(tick.label, padding.left - 6, tick.y)
        }

        // Time ticks (X-axis)
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        for (const tick of timeTicks) {
            // Tick mark
            ctx.beginPath()
            ctx.moveTo(tick.x, padding.top + plotHeight)
            ctx.lineTo(tick.x, padding.top + plotHeight + 4)
            ctx.stroke()
            // Label
            ctx.fillText(tick.label, tick.x, padding.top + plotHeight + 6)
        }

        // Axis labels
        ctx.fillStyle = '#94a3b8'
        ctx.font = '10px system-ui, sans-serif'

        // Y-axis label
        ctx.save()
        ctx.translate(12, padding.top + plotHeight / 2)
        ctx.rotate(-Math.PI / 2)
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText('Frequency (Hz)', 0, 0)
        ctx.restore()

        // X-axis label
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText('Time', padding.left + plotWidth / 2, height - 8)
    }, [data, width, height, minVal, maxVal, plotWidth, plotHeight, padding, freqTicks, timeTicks])

    return (
        <canvas
            ref={canvasRef}
            width={width}
            height={height}
            className="w-full h-auto"
        />
    )
}
