const express = require('express');
const app = express();
app.use(express.json());

app.post('/api/tool', (req, res) => {
    const query = req.body.query || "unknown query";
    res.json({ result: `Archit made thingamabob` });
});

// Also allow GET requests for easier browser testing
app.get('/api/tool', (req, res) => {
    const query = req.query.query || "unknown query";
    res.json({ result: `Archit made thingamabob test via GET` });
});

app.get('/', (req, res) => {
    res.send(`<h2>Web Search Tool</h2><p>This microservice is running safely on dynamic port ${port}</p>`);
});
const port = process.env.PORT || 8005;
app.listen(port, () => {
    console.log(`Web search tool service running on port ${port}`);
});