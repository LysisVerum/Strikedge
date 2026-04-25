// Mock data — replace with real API responses once backend delivers them

export const PERFORMANCE = {
  overall: { bets: 847, wins: 512, losses: 281, pushes: 54, roi: '+9.4%', winRate: '64.6%', units: '+79.6u' },
  byTier: {
    HIGH:   { bets: 203, wins: 148, losses: 42,  pushes: 13, roi: '+18.2%', winRate: '77.9%', units: '+37.0u' },
    MEDIUM: { bets: 389, wins: 241, losses: 124, pushes: 24, roi: '+8.1%',  winRate: '66.0%', units: '+31.5u' },
    LOW:    { bets: 255, wins: 123, losses: 115, pushes: 17, roi: '-2.3%',  winRate: '51.7%', units: '-5.9u'  },
  },
  monthly: [
    { month: 'Nov', roi: 4.2,  wins: 18, losses: 14 },
    { month: 'Dec', roi: 7.8,  wins: 24, losses: 16 },
    { month: 'Jan', roi: 11.2, wins: 31, losses: 18 },
    { month: 'Feb', roi: 6.4,  wins: 28, losses: 19 },
    { month: 'Mar', roi: 13.7, wins: 42, losses: 22 },
    { month: 'Apr', roi: 9.1,  wins: 38, losses: 25 },
  ],
};

export const HISTORY = [
  { id: 1,  date: '2026-04-15', pitcher: 'Gerrit Cole',     bet: 'Over 7.5 K',  line: 7.5,  edge: '+29.2%', confidence: 'HIGH',   result: 'WIN',  actual: 9,  odds: -115 },
  { id: 2,  date: '2026-04-15', pitcher: 'Spencer Strider', bet: 'Over 8.5 K',  line: 8.5,  edge: '+7.3%',  confidence: 'MEDIUM', result: 'LOSS', actual: 7,  odds: -110 },
  { id: 3,  date: '2026-04-14', pitcher: 'Kevin Gausman',   bet: 'Over 6.5 K',  line: 6.5,  edge: '+10.1%', confidence: 'MEDIUM', result: 'WIN',  actual: 8,  odds: -105 },
  { id: 4,  date: '2026-04-14', pitcher: 'Pablo Lopez',     bet: 'Under 6.5 K', line: 6.5,  edge: '-9.4%',  confidence: 'MEDIUM', result: 'WIN',  actual: 5,  odds: -120 },
  { id: 5,  date: '2026-04-13', pitcher: 'Corbin Burnes',   bet: 'Over 6.5 K',  line: 6.5,  edge: '+14.8%', confidence: 'HIGH',   result: 'WIN',  actual: 8,  odds: -115 },
  { id: 6,  date: '2026-04-13', pitcher: 'Zack Wheeler',    bet: 'Over 7.5 K',  line: 7.5,  edge: '+11.2%', confidence: 'HIGH',   result: 'WIN',  actual: 10, odds: -118 },
  { id: 7,  date: '2026-04-12', pitcher: 'Dylan Cease',     bet: 'Over 7.5 K',  line: 7.5,  edge: '+8.9%',  confidence: 'MEDIUM', result: 'PUSH', actual: 8,  odds: -112 },
  { id: 8,  date: '2026-04-12', pitcher: 'Tyler Glasnow',   bet: 'Over 8.5 K',  line: 8.5,  edge: '+6.1%',  confidence: 'MEDIUM', result: 'LOSS', actual: 6,  odds: -110 },
  { id: 9,  date: '2026-04-11', pitcher: 'Freddy Peralta',  bet: 'Over 7.5 K',  line: 7.5,  edge: '+15.3%', confidence: 'HIGH',   result: 'WIN',  actual: 9,  odds: -115 },
  { id: 10, date: '2026-04-11', pitcher: 'Logan Webb',      bet: 'Under 6.5 K', line: 6.5,  edge: '-7.2%',  confidence: 'MEDIUM', result: 'WIN',  actual: 5,  odds: -108 },
  { id: 11, date: '2026-04-10', pitcher: 'Gerrit Cole',     bet: 'Over 8.5 K',  line: 8.5,  edge: '+22.1%', confidence: 'HIGH',   result: 'WIN',  actual: 11, odds: -115 },
  { id: 12, date: '2026-04-10', pitcher: 'Sandy Alcantara', bet: 'Over 6.5 K',  line: 6.5,  edge: '+5.8%',  confidence: 'LOW',    result: 'LOSS', actual: 5,  odds: -110 },
  { id: 13, date: '2026-04-09', pitcher: 'Max Fried',       bet: 'Over 6.5 K',  line: 6.5,  edge: '+9.4%',  confidence: 'MEDIUM', result: 'WIN',  actual: 8,  odds: -112 },
  { id: 14, date: '2026-04-09', pitcher: 'Chris Sale',      bet: 'Over 7.5 K',  line: 7.5,  edge: '+12.7%', confidence: 'HIGH',   result: 'WIN',  actual: 9,  odds: -118 },
  { id: 15, date: '2026-04-08', pitcher: 'Kevin Gausman',   bet: 'Over 6.5 K',  line: 6.5,  edge: '+6.5%',  confidence: 'MEDIUM', result: 'LOSS', actual: 4,  odds: -110 },
];

export const PITCHER_ROSTER = [
  { name: 'Gerrit Cole',      last: 'Cole',      first: 'Gerrit',   team: 'NYY', hand: 'R', k9: 11.2 },
  { name: 'Spencer Strider',  last: 'Strider',   first: 'Spencer',  team: 'ATL', hand: 'R', k9: 12.8 },
  { name: 'Kevin Gausman',    last: 'Gausman',   first: 'Kevin',    team: 'SF',  hand: 'R', k9: 10.1 },
  { name: 'Pablo Lopez',      last: 'Lopez',     first: 'Pablo',    team: 'MIN', hand: 'R', k9: 9.2  },
  { name: 'Corbin Burnes',    last: 'Burnes',    first: 'Corbin',   team: 'BAL', hand: 'R', k9: 10.8 },
  { name: 'Zack Wheeler',     last: 'Wheeler',   first: 'Zack',     team: 'PHI', hand: 'R', k9: 10.4 },
  { name: 'Dylan Cease',      last: 'Cease',     first: 'Dylan',    team: 'SD',  hand: 'R', k9: 11.5 },
  { name: 'Tyler Glasnow',    last: 'Glasnow',   first: 'Tyler',    team: 'LAD', hand: 'R', k9: 11.9 },
  { name: 'Freddy Peralta',   last: 'Peralta',   first: 'Freddy',   team: 'MIL', hand: 'R', k9: 11.3 },
  { name: 'Logan Webb',       last: 'Webb',      first: 'Logan',    team: 'SF',  hand: 'R', k9: 7.8  },
  { name: 'Sandy Alcantara',  last: 'Alcantara', first: 'Sandy',    team: 'MIA', hand: 'R', k9: 8.9  },
  { name: 'Max Fried',        last: 'Fried',     first: 'Max',      team: 'NYY', hand: 'L', k9: 9.1  },
  { name: 'Chris Sale',       last: 'Sale',      first: 'Chris',    team: 'ATL', hand: 'L', k9: 10.7 },
  { name: 'Blake Snell',      last: 'Snell',     first: 'Blake',    team: 'SF',  hand: 'L', k9: 11.1 },
  { name: 'Tarik Skubal',     last: 'Skubal',    first: 'Tarik',    team: 'DET', hand: 'L', k9: 11.8 },
  { name: 'Hunter Brown',     last: 'Brown',     first: 'Hunter',   team: 'HOU', hand: 'R', k9: 9.4  },
  { name: 'Yoshinobu Yamamoto', last: 'Yamamoto', first: 'Yoshinobu', team: 'LAD', hand: 'R', k9: 10.9 },
  { name: 'Paul Skenes',      last: 'Skenes',    first: 'Paul',     team: 'PIT', hand: 'R', k9: 12.1 },
];
