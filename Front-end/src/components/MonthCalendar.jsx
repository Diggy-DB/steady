function MonthCalendar({ onDayClick, selectedDate }){
    const year = 2026;
    const month = 9;
    const firstDayOfweek = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month +1,0).getDate();
    const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const cells = [];
    for(let i = 0; i< firstDayOfweek; i++){
        cells.push(null);
    }
    for(let d =1; d<= daysInMonth; d++){
        cells.push(d);
    }
    function makeDateString(day) {
        const mm = String(month + 1).padStart(2, "0");
        const dd = String(day).padStart(2, "0"); // Pad day with leading zero if necessary
        return `${year}-${mm}-${dd}`;
}
    return (
        <div className= "month-calendar">
            <h2>October 2026</h2>
            <div className = "calendar-grid">
                {weekdays.map((day) => (
                    <div key={day} className="weekday">{day}</div>))}
                    {cells.map((day, index) => {
                        const dateString = day ? makeDateString(day) : null;
                        let className = day ? "day-cell" : "day-cell empty";
                        if (dateString === todayString) className += " today";
                        if (dateString === selectedDate) className += " selected";

                        return (
                            <div
                                key={index}
                                className={className}
                                onClick={() => day && onDayClick(dateString)}
                            >
                                {day}
                                </div>
                        );
                    })}               
                   
            </div>
        </div>
    );
}
const todayString = "2026-10-08";
export default MonthCalendar;