import type { Fiber, Section, Incident, Vehicle, TimeSeriesPoint, IncidentType } from './types'

// ── Map constants ──────────────────────────────────────────────────────────
export const MAP_CENTER: [number, number] = [7.24, 43.72]
export const MAP_ZOOM = 12

// Sampling step per cable (for channel ↔ sampled-index conversion)
export const SAMPLING_STEP: Record<string, number> = { carros: 27, mathis: 12, promenade: 77 }

// ── Real cable coordinates (sampled from infrastructure/clickhouse/cables/*.json) ──

const carrosCoords: [number, number][] = [
    [7.202896, 43.680222], [7.203444, 43.679173], [7.203668, 43.678059],
    [7.204734, 43.677831], [7.204762, 43.67821], [7.20433, 43.679294],
    [7.203901, 43.680378], [7.203466, 43.681461], [7.203032, 43.682544],
    [7.202611, 43.683624], [7.202267, 43.684723], [7.201895, 43.685804],
    [7.201625, 43.686859], [7.201252, 43.687953], [7.200889, 43.68905],
    [7.200468, 43.690133], [7.199904, 43.691184], [7.199331, 43.692233],
    [7.198761, 43.693283], [7.198106, 43.694305], [7.197407, 43.695313],
    [7.196796, 43.696349], [7.19628, 43.697351], [7.194836, 43.697209],
    [7.19332, 43.696971], [7.19196, 43.696636], [7.192039, 43.695733],
    [7.190872, 43.695854], [7.189479, 43.696155], [7.188159, 43.69675],
    [7.186899, 43.697408], [7.186008, 43.698324], [7.185509, 43.699386],
    [7.18518, 43.700369], [7.185077, 43.701491], [7.184939, 43.702611],
    [7.184778, 43.70373], [7.184579, 43.704846], [7.184386, 43.705962],
    [7.184192, 43.707078], [7.183998, 43.708194], [7.183796, 43.709309],
    [7.183583, 43.710423], [7.183371, 43.711537], [7.183158, 43.712651],
    [7.182945, 43.713765], [7.182787, 43.714884], [7.182655, 43.716004],
    [7.182492, 43.717123], [7.182313, 43.71824], [7.182206, 43.719362],
    [7.182049, 43.720481], [7.182117, 43.721441], [7.181951, 43.722559],
    [7.181807, 43.723679], [7.181673, 43.7248], [7.181549, 43.725921],
    [7.181402, 43.72704], [7.18124, 43.728159], [7.18107, 43.729277],
    [7.180922, 43.730397], [7.18077, 43.731516], [7.180615, 43.732635],
    [7.180448, 43.733753], [7.180282, 43.734872], [7.180154, 43.735992],
    [7.180042, 43.737114], [7.18009, 43.738237], [7.180176, 43.73936],
    [7.18045, 43.740467], [7.180727, 43.741574], [7.181099, 43.742665],
    [7.181508, 43.74375], [7.18199, 43.744816], [7.182613, 43.745846],
    [7.183305, 43.746853], [7.184093, 43.747821], [7.184792, 43.748773],
    [7.185471, 43.749443], [7.186429, 43.750385], [7.187392, 43.751324],
    [7.188363, 43.752259], [7.189326, 43.753198], [7.190229, 43.754168],
    [7.191012, 43.755191], [7.19182, 43.756202], [7.192683, 43.75719],
    [7.193683, 43.758108], [7.194787, 43.75896], [7.195976, 43.759751],
    [7.197137, 43.760565], [7.198206, 43.761441], [7.199191, 43.762368],
    [7.200171, 43.763298], [7.201126, 43.764241], [7.201671, 43.765178],
    [7.202663, 43.7661], [7.201968, 43.766638], [7.200532, 43.767088],
    [7.199216, 43.767515], [7.197947, 43.76822], [7.196773, 43.768567],
    [7.195556, 43.769284], [7.196138, 43.769984],
]

const mathisCoords: [number, number][] = [
    [7.203005, 43.680493], [7.203536, 43.678742], [7.205262, 43.677954],
    [7.206739, 43.675417], [7.208587, 43.673218], [7.209801, 43.671645],
    [7.210676, 43.670433], [7.216281, 43.669708], [7.215228, 43.670223],
    [7.217418, 43.669892], [7.218537, 43.669368], [7.216018, 43.668677],
    [7.21671, 43.66907], [7.218106, 43.669438], [7.217551, 43.670626],
    [7.223067, 43.673092], [7.222208, 43.67408], [7.223527, 43.675878],
    [7.224496, 43.677102], [7.226172, 43.678921], [7.228921, 43.680825],
    [7.230675, 43.681938], [7.231591, 43.682407], [7.232486, 43.683192],
    [7.234272, 43.685033], [7.23708, 43.687352], [7.239954, 43.689532],
    [7.241684, 43.690812], [7.242876, 43.691704], [7.24473, 43.693156],
    [7.245104, 43.694362], [7.244297, 43.695572], [7.246009, 43.69629],
    [7.246216, 43.696896], [7.247558, 43.697429], [7.248965, 43.69921],
    [7.250167, 43.700067], [7.251404, 43.700105], [7.252781, 43.700722],
    [7.256907, 43.702905], [7.259267, 43.704724], [7.259602, 43.705725],
    [7.257828, 43.705486], [7.259204, 43.704501], [7.262672, 43.705572],
    [7.265729, 43.706383], [7.266644, 43.706809], [7.270279, 43.708138],
    [7.271538, 43.708245], [7.27645, 43.707233], [7.279608, 43.70707],
    [7.281024, 43.707178], [7.282568, 43.707185],
]

const promenadeCoords: [number, number][] = [
    [7.203671, 43.678053], [7.205913, 43.676443], [7.208342, 43.673525],
    [7.21027, 43.670488], [7.215392, 43.669819], [7.215285, 43.670217],
    [7.217938, 43.669077], [7.21579, 43.668574], [7.218537, 43.669368],
    [7.221192, 43.67004], [7.223699, 43.671823], [7.226272, 43.673939],
    [7.227985, 43.676822], [7.229631, 43.679932], [7.232132, 43.682165],
    [7.234625, 43.684436], [7.236622, 43.686584], [7.239562, 43.688653],
    [7.242588, 43.690608], [7.245848, 43.691565], [7.249897, 43.693033],
    [7.253198, 43.693252], [7.256777, 43.693771], [7.260488, 43.694453],
    [7.264296, 43.694754], [7.268124, 43.694897], [7.270725, 43.695764],
    [7.271601, 43.696986], [7.272085, 43.697286], [7.275667, 43.698276],
    [7.276992, 43.698854], [7.278607, 43.701179], [7.280331, 43.703603],
    [7.282029, 43.706037], [7.283239, 43.708121], [7.283974, 43.710774],
    [7.283633, 43.713476], [7.283486, 43.714238], [7.284398, 43.716596],
    [7.285418, 43.719055], [7.288236, 43.720949], [7.290003, 43.723002],
    [7.288353, 43.725259], [7.285275, 43.726926], [7.283921, 43.729296],
    [7.286478, 43.730697], [7.28749, 43.732592], [7.291006, 43.733699],
    [7.294762, 43.734244], [7.298451, 43.734697],
]

// ── Fibers (2 per cable, matching production FiberLine pattern) ─────────

export const fibers: Fiber[] = [
    { id: 'carros:0', parentCableId: 'carros', direction: 0, name: 'Carros', color: '#6366f1', totalChannels: 3200, coordinates: carrosCoords },
    { id: 'carros:1', parentCableId: 'carros', direction: 1, name: 'Carros', color: '#818cf8', totalChannels: 3200, coordinates: carrosCoords },
    { id: 'mathis:0', parentCableId: 'mathis', direction: 0, name: 'Mathis', color: '#0ea5e9', totalChannels: 1255, coordinates: mathisCoords },
    { id: 'mathis:1', parentCableId: 'mathis', direction: 1, name: 'Mathis', color: '#38bdf8', totalChannels: 1255, coordinates: mathisCoords },
    { id: 'promenade:0', parentCableId: 'promenade', direction: 0, name: 'Promenade', color: '#8b5cf6', totalChannels: 8000, coordinates: promenadeCoords },
    { id: 'promenade:1', parentCableId: 'promenade', direction: 1, name: 'Promenade', color: '#a78bfa', totalChannels: 8000, coordinates: promenadeCoords },
]

// ── Helpers ─────────────────────────────────────────────────────────────

function generateHistory(base: number, variance: number, len: number): number[] {
    return Array.from({ length: len }, () =>
        Math.round(base + (Math.random() - 0.5) * 2 * variance)
    )
}

export function getSpeedColor(speed: number): string {
    if (speed >= 80) return '#22c55e'
    if (speed >= 60) return '#eab308'
    if (speed >= 30) return '#f97316'
    return '#ef4444'
}

// ── Sections (channel-based, referencing real fibers) ───────────────────

export const initialSections: Section[] = [
    {
        id: 'section:carros:0:270-1350',
        fiberId: 'carros:0',
        name: 'Carros - Zone Sud',
        startChannel: 270,
        endChannel: 1350,
        avgSpeed: 95,
        flow: 1840,
        occupancy: 22,
        travelTime: 3.1,
        speedHistory: generateHistory(95, 15, 30),
        countHistory: generateHistory(1840, 200, 30),
    },
    {
        id: 'section:carros:0:1620-2700',
        fiberId: 'carros:0',
        name: 'Carros - Zone Nord',
        startChannel: 1620,
        endChannel: 2700,
        avgSpeed: 108,
        flow: 1560,
        occupancy: 16,
        travelTime: 2.4,
        speedHistory: generateHistory(108, 12, 30),
        countHistory: generateHistory(1560, 180, 30),
    },
    {
        id: 'section:mathis:0:120-600',
        fiberId: 'mathis:0',
        name: 'Mathis - Descente',
        startChannel: 120,
        endChannel: 600,
        avgSpeed: 72,
        flow: 1200,
        occupancy: 34,
        travelTime: 4.2,
        speedHistory: generateHistory(72, 18, 30),
        countHistory: generateHistory(1200, 150, 30),
    },
    {
        id: 'section:promenade:0:770-3080',
        fiberId: 'promenade:0',
        name: 'Promenade - Littoral',
        startChannel: 770,
        endChannel: 3080,
        avgSpeed: 45,
        flow: 980,
        occupancy: 52,
        travelTime: 6.8,
        speedHistory: generateHistory(45, 12, 30),
        countHistory: generateHistory(980, 120, 30),
    },
    {
        id: 'section:promenade:0:3850-5390',
        fiberId: 'promenade:0',
        name: 'Promenade - Corniche',
        startChannel: 3850,
        endChannel: 5390,
        avgSpeed: 62,
        flow: 740,
        occupancy: 28,
        travelTime: 5.1,
        speedHistory: generateHistory(62, 14, 30),
        countHistory: generateHistory(740, 100, 30),
    },
]

// ── Incidents (locations picked from real coordinates) ──────────────────

export const incidents: Incident[] = [
    {
        id: 'inc1',
        fiberId: 'promenade:0',
        sectionId: 'section:promenade:0:770-3080',
        type: 'accident',
        severity: 'critical',
        title: 'Multi-vehicle collision',
        description: 'Three-vehicle collision blocking two lanes near the Promenade littoral section. Emergency services on site.',
        location: [7.249897, 43.693033],
        timestamp: '2026-03-03T14:23:00Z',
        resolved: false,
    },
    {
        id: 'inc2',
        fiberId: 'carros:0',
        sectionId: 'section:carros:0:1620-2700',
        type: 'construction',
        severity: 'high',
        title: 'Lane closure - maintenance',
        description: 'Right lane closed for road surface maintenance on Carros Nord. Expected to reopen at 18:00.',
        location: [7.181807, 43.723679],
        timestamp: '2026-03-03T08:00:00Z',
        resolved: false,
    },
    {
        id: 'inc3',
        fiberId: 'mathis:0',
        sectionId: 'section:mathis:0:120-600',
        type: 'anomaly',
        severity: 'medium',
        title: 'Unusual vibration pattern',
        description: 'DAS sensors detecting abnormal vibration signature. Possible structural concern on the Mathis descent.',
        location: [7.226172, 43.678921],
        timestamp: '2026-03-03T11:45:00Z',
        resolved: false,
    },
    {
        id: 'inc4',
        fiberId: 'carros:0',
        sectionId: 'section:carros:0:270-1350',
        type: 'weather',
        severity: 'medium',
        title: 'Heavy rain warning',
        description: 'Reduced visibility and wet road conditions. Speed advisory in effect on Carros Sud.',
        location: [7.200468, 43.690133],
        timestamp: '2026-03-03T12:30:00Z',
        resolved: false,
    },
    {
        id: 'inc5',
        fiberId: 'promenade:0',
        sectionId: 'section:promenade:0:3850-5390',
        type: 'intrusion',
        severity: 'low',
        title: 'Pedestrian near roadway',
        description: 'Pedestrian detected near the Corniche section. Patrol dispatched.',
        location: [7.283974, 43.710774],
        timestamp: '2026-03-03T13:15:00Z',
        resolved: true,
    },
    {
        id: 'inc6',
        fiberId: 'promenade:0',
        sectionId: 'section:promenade:0:770-3080',
        type: 'anomaly',
        severity: 'low',
        title: 'Sensor calibration drift',
        description: 'Minor calibration drift detected on Promenade fiber segment. Scheduled for next maintenance window.',
        location: [7.264296, 43.694754],
        timestamp: '2026-03-03T09:00:00Z',
        resolved: true,
    },
]

// ── Vehicles (spread across fibers, various speeds) ─────────────────────

export const vehicles: Vehicle[] = [
    // Carros - mostly fast
    { id: 'v1', fiberId: 'carros:0', position: [7.201895, 43.685804], speed: 105, direction: 0 },
    { id: 'v2', fiberId: 'carros:0', position: [7.198106, 43.694305], speed: 92, direction: 0 },
    { id: 'v3', fiberId: 'carros:1', position: [7.184386, 43.705962], speed: 115, direction: 1 },
    { id: 'v4', fiberId: 'carros:0', position: [7.182655, 43.716004], speed: 88, direction: 0 },
    { id: 'v5', fiberId: 'carros:1', position: [7.18199, 43.744816], speed: 78, direction: 1 },
    // Mathis - moderate
    { id: 'v6', fiberId: 'mathis:0', position: [7.208587, 43.673218], speed: 72, direction: 0 },
    { id: 'v7', fiberId: 'mathis:0', position: [7.234272, 43.685033], speed: 65, direction: 0 },
    { id: 'v8', fiberId: 'mathis:1', position: [7.256907, 43.702905], speed: 55, direction: 1 },
    { id: 'v9', fiberId: 'mathis:0', position: [7.270279, 43.708138], speed: 70, direction: 0 },
    // Promenade - mixed, some slow (congested)
    { id: 'v10', fiberId: 'promenade:0', position: [7.232132, 43.682165], speed: 42, direction: 0 },
    { id: 'v11', fiberId: 'promenade:0', position: [7.253198, 43.693252], speed: 28, direction: 0 },
    { id: 'v12', fiberId: 'promenade:1', position: [7.268124, 43.694897], speed: 35, direction: 1 },
    { id: 'v13', fiberId: 'promenade:0', position: [7.283239, 43.708121], speed: 58, direction: 0 },
    { id: 'v14', fiberId: 'promenade:0', position: [7.288236, 43.720949], speed: 22, direction: 0 },
    { id: 'v15', fiberId: 'promenade:1', position: [7.294762, 43.734244], speed: 85, direction: 1 },
]

// ── Time series (60 min of mock data) ───────────────────────────────────

function generateTimeSeries(length: number): TimeSeriesPoint[] {
    const now = new Date('2026-03-03T15:00:00Z')
    return Array.from({ length }, (_, i) => {
        const t = new Date(now.getTime() - (length - 1 - i) * 60_000)
        const hour = t.getHours()
        const rushFactor = (hour >= 7 && hour <= 9) || (hour >= 17 && hour <= 19) ? 1.3 : 1
        return {
            time: t.toISOString().slice(11, 16),
            speed: Math.round(80 + Math.sin(i / 5) * 20 + (Math.random() - 0.5) * 10),
            flow: Math.round((1200 + Math.cos(i / 8) * 400 + (Math.random() - 0.5) * 200) * rushFactor),
            occupancy: Math.round(25 + Math.sin(i / 6) * 15 + (Math.random() - 0.5) * 8),
        }
    })
}

export const timeSeries: TimeSeriesPoint[] = generateTimeSeries(60)

// ── Severity / style constants ──────────────────────────────────────────

export const severityColor: Record<string, string> = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#f59e0b',
    low: '#22c55e',
}

export const incidentTypeIcon: Record<IncidentType, string> = {
    accident: '!',
    construction: '\u2692',
    weather: '\u2602',
    anomaly: '?',
    intrusion: '\u26A0',
}

export const chartColors = {
    speed: { label: 'Speed', unit: 'km/h', color: '#6366f1' },
    flow: { label: 'Flow', unit: 'veh/h', color: '#8b5cf6' },
    occupancy: { label: 'Occupancy', unit: '%', color: '#0ea5e9' },
}
