import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import Home from "./routes/Home";
import SourcesLookups from "./routes/SourcesLookups";
import SourceSelection from "./routes/ingestion/SourceSelection";
import UploadFlow from "./routes/ingestion/UploadFlow";
import SapUpload from "./routes/ingestion/SapUpload";
import UtilityUpload from "./routes/ingestion/UtilityUpload";
import TravelSync from "./routes/ingestion/TravelSync";
import BatchList from "./routes/ingestion/BatchList";
import BatchDetail from "./routes/ingestion/BatchDetail";
import Summary from "./routes/review/Summary";
import ActivityList from "./routes/review/ActivityList";
import ActivityDetail from "./routes/review/ActivityDetail";
import PageHeader from "./components/PageHeader";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Home />} />
        <Route path="/ingestion" element={<SourceSelection />} />
        <Route path="/ingestion/upload" element={<UploadFlow />} />
        <Route path="/ingestion/upload-sap" element={<SapUpload />} />
        <Route path="/ingestion/upload-utility" element={<UtilityUpload />} />
        <Route path="/ingestion/travel-sync" element={<TravelSync />} />
        <Route path="/ingestion/batches" element={<BatchList />} />
        <Route path="/ingestion/batches/:id" element={<BatchDetail />} />
        <Route path="/review" element={<Summary />} />
        <Route path="/review/activities" element={<ActivityList />} />
        <Route path="/review/activities/:id" element={<ActivityDetail />} />
        <Route path="/sources" element={<SourcesLookups />} />
        <Route path="/locked-records" element={<Navigate to="/review/activities?locked=true" replace />} />
        <Route
          path="*"
          element={
            <div>
              <PageHeader
                title="Page not found"
                description="This workspace page does not exist. Use the sidebar to return to ingestion or analyst review."
              />
            </div>
          }
        />
      </Route>
    </Routes>
  );
}
