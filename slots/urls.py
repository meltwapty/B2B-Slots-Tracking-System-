from django.urls import path
from . import views

urlpatterns = [
    path("",              views.dashboard_ui,                  name="dashboard-ui"),
    path("api/dashboard/",views.DashboardView.as_view(),       name="dashboard"),
    path("api/sync/",     views.SyncTriggerView.as_view(),     name="sync-trigger"),
    path("api/sync/status/", views.SyncStatusView.as_view(),   name="sync-status"),
    path("api/contracts/",views.ContractsListView.as_view(),   name="contracts"),
    path("api/oos/",      views.OOSListView.as_view(),         name="oos-entries"),
]
