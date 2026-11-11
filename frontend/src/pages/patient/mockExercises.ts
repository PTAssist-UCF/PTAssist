export interface AssignedExercise {
  id: string;
  name: string;
  displayName: string;
  kind: 'reps' | 'hold';
  targetSets: number;
  targetPerSet: number;
  unit: 'reps' | 'seconds';
  targetDescription: string;
  completedSets: number;
  completedUnits: number;
  totalUnits: number;
  progressPercent: number;
  progressDescription: string;
  instructions: string;
  imageUrl: string;
}

// Clean, high-contrast SVG illustrations for each exercise
function createSvgDataUrl(title: string, postureSvg: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 240" width="100%" height="100%">
    <defs>
      <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#f8f9fa"/>
        <stop offset="100%" stop-color="#e9ecef"/>
      </linearGradient>
    </defs>
    <rect width="400" height="240" rx="12" fill="url(#bg)"/>
    <rect x="10" y="10" width="380" height="220" rx="8" fill="none" stroke="#099268" stroke-width="2" stroke-dasharray="6,4" opacity="0.4"/>
    <g transform="translate(100, 30)">
      ${postureSvg}
    </g>
    <text x="200" y="215" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif" font-size="16" font-weight="600" fill="#099268" text-anchor="middle">${title}</text>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

// 1. Squat illustration
const squatSvg = `
  <!-- Head -->
  <circle cx="90" cy="30" r="14" fill="#099268" />
  <!-- Torso leaning slightly -->
  <line x1="90" y1="44" x2="80" y2="90" stroke="#099268" stroke-width="8" stroke-linecap="round" />
  <!-- Arms extended for balance -->
  <line x1="88" y1="56" x2="135" y2="56" stroke="#099268" stroke-width="6" stroke-linecap="round" />
  <!-- Thigh (bent at ~90 deg) -->
  <line x1="80" y1="90" x2="40" y2="90" stroke="#099268" stroke-width="8" stroke-linecap="round" />
  <!-- Shin (vertical back to ground) -->
  <line x1="40" y1="90" x2="45" y2="140" stroke="#099268" stroke-width="8" stroke-linecap="round" />
  <!-- Feet -->
  <line x1="40" y1="140" x2="65" y2="140" stroke="#099268" stroke-width="6" stroke-linecap="round" />
`;

// 2. Shoulder Abduction illustration
const shoulderAbductionSvg = `
  <!-- Head -->
  <circle cx="100" cy="25" r="14" fill="#099268" />
  <!-- Torso upright -->
  <line x1="100" y1="39" x2="100" y2="105" stroke="#099268" stroke-width="8" stroke-linecap="round" />
  <!-- Abducted Arm raised laterally -->
  <line x1="100" y1="50" x2="160" y2="50" stroke="#099268" stroke-width="7" stroke-linecap="round" />
  <path d="M 140 70 A 25 25 0 0 0 155 50" fill="none" stroke="#20c997" stroke-width="3" stroke-dasharray="3,3" />
  <!-- Resting Arm -->
  <line x1="100" y1="50" x2="80" y2="95" stroke="#099268" stroke-width="6" stroke-linecap="round" />
  <!-- Legs -->
  <line x1="100" y1="105" x2="85" y2="155" stroke="#099268" stroke-width="7" stroke-linecap="round" />
  <line x1="100" y1="105" x2="115" y2="155" stroke="#099268" stroke-width="7" stroke-linecap="round" />
`;

// 3. Plank illustration
const plankSvg = `
  <!-- Head -->
  <circle cx="45" cy="65" r="13" fill="#099268" />
  <!-- Torso & hips in a straight line -->
  <line x1="45" y1="75" x2="150" y2="85" stroke="#099268" stroke-width="8" stroke-linecap="round" />
  <!-- Forearms on floor -->
  <line x1="60" y1="76" x2="65" y2="115" stroke="#099268" stroke-width="6" stroke-linecap="round" />
  <line x1="65" y1="115" x2="85" y2="115" stroke="#099268" stroke-width="6" stroke-linecap="round" />
  <!-- Legs extending back -->
  <line x1="150" y1="85" x2="175" y2="115" stroke="#099268" stroke-width="8" stroke-linecap="round" />
  <!-- Ground floor line -->
  <line x1="20" y1="120" x2="190" y2="120" stroke="#20c997" stroke-width="3" stroke-linecap="round" opacity="0.6"/>
`;

// 4. Side Leg Raise illustration
const sideLegRaiseSvg = `
  <!-- Head lying on side -->
  <circle cx="45" cy="95" r="13" fill="#099268" />
  <!-- Torso along mat -->
  <line x1="55" y1="100" x2="110" y2="105" stroke="#099268" stroke-width="8" stroke-linecap="round" />
  <!-- Bottom supporting leg -->
  <line x1="110" y1="105" x2="170" y2="105" stroke="#099268" stroke-width="7" stroke-linecap="round" />
  <!-- Raised top leg -->
  <line x1="110" y1="105" x2="160" y2="60" stroke="#099268" stroke-width="8" stroke-linecap="round" />
  <path d="M 145 95 A 30 30 0 0 0 152 75" fill="none" stroke="#20c997" stroke-width="3" stroke-dasharray="3,3" />
`;

// 5. Cat-Cow illustration
const catCowSvg = `
  <!-- Head looking down/forward -->
  <circle cx="50" cy="65" r="13" fill="#099268" />
  <!-- Neck & Arched spine -->
  <path d="M 50 72 Q 95 45 135 78" fill="none" stroke="#099268" stroke-width="8" stroke-linecap="round" />
  <!-- Front arms (perpendicular to ground) -->
  <line x1="68" y1="70" x2="68" y2="120" stroke="#099268" stroke-width="7" stroke-linecap="round" />
  <!-- Thighs / rear legs (perpendicular to ground) -->
  <line x1="135" y1="78" x2="135" y2="120" stroke="#099268" stroke-width="7" stroke-linecap="round" />
  <!-- Mat line -->
  <line x1="30" y1="125" x2="160" y2="125" stroke="#20c997" stroke-width="3" stroke-linecap="round" opacity="0.6"/>
`;

// Sample data until the page loads the patient's real plan from the API.
// The ids are made up and only used as React keys: they are not real plan exercise ids,
// so never send them to the API (POST /sessions would answer 404 "Plan exercise not found").
export const MOCK_ASSIGNED_EXERCISES: AssignedExercise[] = [
  {
    id: 'a1b2c3d4-e5f6-7890-1234-56789abcdef0',
    name: 'squat',
    displayName: 'Squat',
    kind: 'reps',
    targetSets: 3,
    targetPerSet: 10,
    unit: 'reps',
    targetDescription: '3 sets × 10 reps',
    completedSets: 2,
    completedUnits: 20,
    totalUnits: 30,
    progressPercent: 67,
    progressDescription: '2 of 3 sets completed today (20 of 30 reps). 1 set remaining.',
    instructions:
      'Keep your back straight, feet shoulder-width apart, and lower your hips until thighs are parallel to the ground.',
    imageUrl: createSvgDataUrl('Squat Posture', squatSvg),
  },
  {
    id: 'b2c3d4e5-f6a7-8901-2345-6789abcdef01',
    name: 'shoulder_abduction',
    displayName: 'Shoulder Abduction',
    kind: 'reps',
    targetSets: 2,
    targetPerSet: 10,
    unit: 'reps',
    targetDescription: '2 sets × 10 reps',
    completedSets: 1,
    completedUnits: 10,
    totalUnits: 20,
    progressPercent: 50,
    progressDescription: '1 of 2 sets completed today (10 of 20 reps). 1 set remaining.',
    instructions:
      'Standing upright, raise your arm laterally up to shoulder height without hiking your shoulder.',
    imageUrl: createSvgDataUrl('Shoulder Abduction Posture', shoulderAbductionSvg),
  },
  {
    id: 'c3d4e5f6-a7b8-9012-3456-789abcdef012',
    name: 'plank',
    displayName: 'Plank',
    kind: 'hold',
    targetSets: 3,
    targetPerSet: 30,
    unit: 'seconds',
    targetDescription: '3 sets × 30s hold',
    completedSets: 3,
    completedUnits: 90,
    totalUnits: 90,
    progressPercent: 100,
    progressDescription: 'All 3 sets completed today (90 of 90 seconds held). Target achieved!',
    instructions:
      'Support your body on forearms and toes, maintaining a rigid straight line from head to heels.',
    imageUrl: createSvgDataUrl('Plank Posture', plankSvg),
  },
  {
    id: 'd4e5f6a7-b8c9-0123-4567-89abcdef0123',
    name: 'side_leg_raise',
    displayName: 'Side Leg Raise',
    kind: 'reps',
    targetSets: 2,
    targetPerSet: 20,
    unit: 'reps',
    targetDescription: '2 sets × 20 reps',
    completedSets: 0,
    completedUnits: 0,
    totalUnits: 40,
    progressPercent: 0,
    progressDescription: '0 of 2 sets completed today. Not started yet.',
    instructions:
      'Lie on your side with hips stacked, raising your top leg upward in a controlled, smooth motion.',
    imageUrl: createSvgDataUrl('Side Leg Raise Posture', sideLegRaiseSvg),
  },
  {
    id: 'e5f6a7b8-c9d0-1234-5678-9abcdef01234',
    name: 'cat_cow',
    displayName: 'Cat-Cow',
    kind: 'reps',
    targetSets: 2,
    targetPerSet: 8,
    unit: 'reps',
    targetDescription: '2 sets × 8 reps',
    completedSets: 1,
    completedUnits: 8,
    totalUnits: 16,
    progressPercent: 50,
    progressDescription: '1 of 2 sets completed today (8 of 16 reps). 1 set remaining.',
    instructions:
      'Start on hands and knees, alternating between arching your spine upward (cat) and dropping your belly (cow).',
    imageUrl: createSvgDataUrl('Cat-Cow Posture', catCowSvg),
  },
];
