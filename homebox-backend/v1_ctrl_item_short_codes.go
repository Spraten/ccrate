package v1

import (
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/hay-kot/httpkit/errchain"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
	"github.com/sysadminsmedia/homebox/backend/internal/data/repo"
	"github.com/sysadminsmedia/homebox/backend/internal/web/adapters"
)

// HandleEntityByShortCode performs an exact, active-collection item lookup.
func (ctrl *V1Controller) HandleEntityByShortCode() errchain.HandlerFunc {
	fn := func(r *http.Request) (repo.EntityOut, error) {
		auth := services.NewContext(r.Context())
		return ctrl.repo.Entities.GetByShortCode(r.Context(), auth.GID, chi.URLParam(r, "code"))
	}
	return adapters.Command(fn, http.StatusOK)
}
