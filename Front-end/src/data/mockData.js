export const mockEvents = [
  {
    event_id: 1,
    name: "Calculus Class",
    start_time: "10:00",
    end_time: "12:00",
    start_date: "2026-10-05",
    end_date: "2026-10-05",
    recurrence_rule: null,
    changeable: false,
    created_by: "USER",
  },
  {
    event_id: 2,
    name: "Study Session",
    start_time: "18:00",
    end_time: "19:00",
    start_date: "2026-10-05",
    end_date: "2026-10-05",
    recurrence_rule: null,
    changeable: true,
    created_by: "USER",
  },
  // inside mockEvents
{
  event_id: 3,
  name: "Team Meeting",
  start_time: "14:00",
  end_time: "15:00",
  start_date: "2026-10-08",
  end_date: "2026-10-08",
  recurrence_rule: null,
  changeable: false,
  created_by: "USER",
},
{
  event_id: 4,
  name: "Gym",
  start_time: "17:00",
  end_time: "18:00",
  start_date: "2026-10-09",
  end_date: "2026-10-09",
  recurrence_rule: null,
  changeable: true,
  created_by: "AI",
},
];

export const mockTasks = [
  {
    task_id: 1,
    name: "Finish homework",
    description: "Problem set 4",
    date: "2026-10-05",
    status: "IN_PROGRESS",

    changeable: true,
    created_by: "USER",
  },
  // inside mockTasks
{
  task_id: 2,
  name: "Read chapter 5",
  description: "Biology textbook",
  date: "2026-10-08",
  status: "NOT_STARTED",
  changeable: true,
  created_by: "USER",
},
{
  task_id: 3,
  name: "Submit lab report",
  description: "Due at midnight",
  date: "2026-10-09",
  status: "COMPLETED",
  changeable: false,
  created_by: "USER",
},
];

export const mockJournals = [
  {
    journal_id: 1,
    date: "2026-10-05",
    information: "Felt productive today.",
  },
  {
  journal_id: 2,
  date: "2026-10-08",
  information: "Busy day, but I got the meeting done.",
},
{
  journal_id: 3,
  date: "2026-10-09",
  information: "Great workout at the gym.",
}
];

export const mockAIOverview = {
  succeeded: "You completed 3 of 4 tasks yesterday.",
  missed: "Your reading session was skipped.",
  suggestion: "Try moving reading to tonight, since you prefer evenings.",
  motivation: "Small steps every day add up.",
  
};