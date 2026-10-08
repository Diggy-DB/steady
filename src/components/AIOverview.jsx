function AIOverview({ overview }){
    return (
        <div className = "ai-overview">
            <h2>Your Daily Overview</h2>
            <p>- {overview.succeeded}</p>
            <p>- {overview.missed} </p>
            <p>- {overview.suggestion} </p>
            <p><em>{overview.motivation} </em></p>
        </div>
    );
}
export default AIOverview;