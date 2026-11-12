// A profile counts as filled in once any of the "about you" fields is set (as in the old profile panel).
export const profileIsEmpty = (p) =>
  !p.priorities?.length && !p.hobbies?.length && !(p.additional_information ?? "").trim();
